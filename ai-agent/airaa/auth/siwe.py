"""EIP-4361 (Sign-In with Ethereum): parse the message and verify its signature.

Externally owned accounts are verified by recovering the signer (EIP-191 ``personal_sign``). Smart-contract
wallets (e.g. Coinbase Smart Wallet) cannot sign directly, so their signature is checked on-chain with
EIP-1271 ``isValidSignature`` over an ``eth_call``.

Not supported: ERC-6492 signatures from smart wallets that are not deployed yet. They are detected and
rejected with a clear message instead of failing as "bad signature".
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import httpx
from eth_account import Account
from eth_account.messages import encode_defunct
from eth_utils import keccak

logger = logging.getLogger(__name__)

ERC1271_MAGIC = "0x1626ba7e"
ERC6492_SUFFIX = bytes.fromhex("6492" * 16)

# Public RPCs for EIP-1271 checks; override per chain with AIRAA_RPC_URLS='{"8453": "https://..."}'.
DEFAULT_RPC_URLS: Dict[int, str] = {
    1: "https://ethereum-rpc.publicnode.com",
    11155111: "https://ethereum-sepolia-rpc.publicnode.com",
    8453: "https://mainnet.base.org",
    84532: "https://sepolia.base.org",
    43113: "https://api.avax-test.network/ext/bc/C/rpc",
    137: "https://polygon-bor-rpc.publicnode.com",
}

_ADDRESS = re.compile(r"^0x[a-fA-F0-9]{40}$")
_HEADER = re.compile(r"^(?:(?P<scheme>[a-zA-Z][a-zA-Z0-9+.-]*)://)?(?P<domain>[^\s/?#]+) wants you to sign in with your Ethereum account:$")
_NONCE = re.compile(r"^[a-zA-Z0-9]{8,64}$")
_MAX_AGE = timedelta(minutes=10)
_CLOCK_SKEW = timedelta(minutes=2)


class SiweError(ValueError):
    """The message or signature is not acceptable. The text is safe to show to the user."""


@dataclass
class SiweMessage:
    domain: str
    address: str
    uri: str
    version: str
    chain_id: int
    nonce: str
    issued_at: datetime
    statement: Optional[str] = None
    scheme: Optional[str] = None
    expiration_time: Optional[datetime] = None
    not_before: Optional[datetime] = None
    request_id: Optional[str] = None
    resources: List[str] = field(default_factory=list)


def _time(value: str, label: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        raise SiweError(f"{label} is not a valid timestamp") from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def parse_message(text: str) -> SiweMessage:
    """Parse an EIP-4361 message. Raises :class:`SiweError` on anything malformed."""
    if not isinstance(text, str) or not text or len(text) > 4000:
        raise SiweError("Sign-in message is missing or too long")
    lines = text.split("\n")
    header = _HEADER.match(lines[0]) if lines else None
    if not header or len(lines) < 6:
        raise SiweError("Sign-in message is not a valid EIP-4361 message")
    address = lines[1].strip()
    if not _ADDRESS.match(address) or lines[2] != "":
        raise SiweError("Sign-in message has an invalid address")

    # After the address block the spec has an optional statement. Without one, there are two blank lines before
    # "URI:" (viem and the siwe library both emit that); a single blank line is tolerated too.
    idx = 3
    statement: Optional[str] = None
    if lines[idx] == "" and lines[idx + 1:idx + 2] and lines[idx + 1].startswith("URI: "):
        idx += 1
    elif not lines[idx].startswith("URI: "):
        statement = lines[idx]
        if not statement or lines[idx + 1:idx + 2] != [""]:
            raise SiweError("Sign-in message is malformed near the statement")
        idx += 2

    fields: Dict[str, str] = {}
    resources: List[str] = []
    in_resources = False
    for line in lines[idx:]:
        if in_resources:
            if not line.startswith("- "):
                raise SiweError("Sign-in message has a malformed resource list")
            resources.append(line[2:])
        elif line == "Resources:":
            in_resources = True
        else:
            key, sep, value = line.partition(": ")
            if not sep:
                raise SiweError("Sign-in message has a malformed field")
            fields[key] = value

    for required in ("URI", "Version", "Chain ID", "Nonce", "Issued At"):
        if required not in fields:
            raise SiweError(f"Sign-in message is missing '{required}'")
    if fields["Version"] != "1":
        raise SiweError("Unsupported sign-in message version")
    try:
        chain_id = int(fields["Chain ID"])
    except ValueError:
        raise SiweError("Sign-in message has an invalid chain id") from None
    if not _NONCE.match(fields["Nonce"]):
        raise SiweError("Sign-in message has an invalid nonce")

    return SiweMessage(
        domain=header.group("domain"), scheme=header.group("scheme"), address=address, statement=statement,
        uri=fields["URI"], version=fields["Version"], chain_id=chain_id, nonce=fields["Nonce"],
        issued_at=_time(fields["Issued At"], "Issued At"),
        expiration_time=_time(fields["Expiration Time"], "Expiration Time") if "Expiration Time" in fields else None,
        not_before=_time(fields["Not Before"], "Not Before") if "Not Before" in fields else None,
        request_id=fields.get("Request ID"), resources=resources,
    )


def validate_message(message: SiweMessage, allowed_domains: tuple, now: Optional[datetime] = None) -> None:
    """Domain binding and time-window checks. The nonce is checked separately (it is stateful)."""
    now = now or datetime.now(timezone.utc)
    if message.domain.lower() not in {d.lower() for d in allowed_domains}:
        raise SiweError("Sign-in message was issued for a different site")
    if message.issued_at > now + _CLOCK_SKEW:
        raise SiweError("Sign-in message is dated in the future")
    if now - message.issued_at > _MAX_AGE:
        raise SiweError("Sign-in message has expired; try again")
    if message.expiration_time and now > message.expiration_time:
        raise SiweError("Sign-in message has expired; try again")
    if message.not_before and now + _CLOCK_SKEW < message.not_before:
        raise SiweError("Sign-in message is not valid yet")


# ---------------------------------------------------------------- signatures
def _decode_signature(signature: str) -> bytes:
    if not isinstance(signature, str) or not re.fullmatch(r"0x(?:[a-fA-F0-9]{2})+", signature) or len(signature) > 20000:
        raise SiweError("Signature must be a 0x-prefixed hex string")
    return bytes.fromhex(signature[2:])


def _eoa_recover(text: str, signature: bytes) -> Optional[str]:
    try:
        return Account.recover_message(encode_defunct(text=text), signature=signature).lower()
    except Exception:  # noqa: BLE001 - any recovery failure just means "not an EOA signature"
        return None


def message_hash(text: str) -> bytes:
    """EIP-191 hash of the message: what a smart wallet's isValidSignature receives."""
    data = text.encode("utf-8")
    return keccak(b"\x19Ethereum Signed Message:\n" + str(len(data)).encode() + data)


def _encode_is_valid_signature(digest: bytes, signature: bytes) -> str:
    padded = signature + b"\x00" * (-len(signature) % 32)
    return (ERC1271_MAGIC[2:] + digest.hex() + (64).to_bytes(32, "big").hex()
            + len(signature).to_bytes(32, "big").hex() + padded.hex())


def rpc_url_for(chain_id: int, overrides_json: str = "") -> Optional[str]:
    overrides: Dict[str, str] = {}
    if overrides_json:
        try:
            overrides = {str(k): str(v) for k, v in json.loads(overrides_json).items()}
        except (ValueError, AttributeError):
            logger.warning("AIRAA_RPC_URLS is not a valid JSON object; ignoring it")
    return overrides.get(str(chain_id)) or DEFAULT_RPC_URLS.get(chain_id)


def _erc1271_valid(address: str, digest: bytes, signature: bytes, rpc_url: str, timeout: float = 8.0) -> bool:
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "eth_call",
        "params": [{"to": address, "data": "0x" + _encode_is_valid_signature(digest, signature)}, "latest"],
    }
    try:
        response = httpx.post(rpc_url, json=payload, timeout=timeout)
        result = response.json().get("result", "")
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("EIP-1271 check failed to reach the RPC: %s", exc)
        raise SiweError("Could not verify the smart-wallet signature right now; try again") from None
    return isinstance(result, str) and result.lower().startswith(ERC1271_MAGIC)


def verify_signature(text: str, signature_hex: str, address: str, chain_id: int, rpc_urls_json: str = "") -> str:
    """Return how the signature was verified (``"eoa"`` or ``"erc1271"``) or raise :class:`SiweError`."""
    signature = _decode_signature(signature_hex)
    if signature.endswith(ERC6492_SUFFIX):
        raise SiweError("This smart wallet is not deployed on-chain yet; make a transaction with it first, then sign in")

    if len(signature) == 65 and _eoa_recover(text, signature) == address.lower():
        return "eoa"

    rpc_url = rpc_url_for(chain_id, rpc_urls_json)
    if rpc_url is None:
        raise SiweError("Signature does not match the address (and smart-wallet checks are not available on this chain)")
    if _erc1271_valid(address, message_hash(text), signature, rpc_url):
        return "erc1271"
    raise SiweError("Signature does not match the address")
