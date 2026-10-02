"""Safe fetching of user-supplied URLs.

The agent reads web pages the user names, so a fetch must never reach this server's own network:
``http://localhost``, cloud metadata (``169.254.169.254``), private ranges, etc. Every hop of a
redirect chain is re-checked, because a public URL can redirect to a private one.
"""
from __future__ import annotations

import asyncio
import html
import ipaddress
import re
import socket
from typing import Optional, Tuple
from urllib.parse import urljoin, urlsplit

import httpx

MAX_REDIRECTS = 3
MAX_BYTES = 2_000_000
_TAGS = re.compile(r"<[^>]+>")
_DROP = re.compile(r"<(script|style|noscript|svg|nav|footer|header|form)[^>]*>.*?</\1>", re.I | re.S)
_SPACE = re.compile(r"[ \t\r\f\v]+")
_LINES = re.compile(r"\n\s*\n+")
_TITLE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)


class UnsafeURL(ValueError):
    pass


async def check_public_url(url: str) -> str:
    """Raise :class:`UnsafeURL` unless ``url`` is http(s) on a standard port and resolves only to public IPs."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise UnsafeURL("Only http(s) URLs with a host name are allowed")
    if parts.username or parts.password:
        raise UnsafeURL("URLs with credentials are not allowed")
    if parts.port not in (None, 80, 443):
        raise UnsafeURL("Only standard web ports are allowed")
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, parts.hostname, parts.port or 443, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise UnsafeURL(f"Cannot resolve host: {parts.hostname}") from exc
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL(f"Host resolves to a non-public address: {parts.hostname}")
    return url


def html_to_text(raw: str) -> Tuple[str, str]:
    """Very small HTML -> (title, text) reducer. Good enough to give a model the gist of a page."""
    title_match = _TITLE.search(raw)
    title = html.unescape(_TAGS.sub("", title_match.group(1))).strip() if title_match else ""
    body = _DROP.sub(" ", raw)
    body = re.sub(r"<(br|/p|/div|/li|/h[1-6]|/tr)[^>]*>", "\n", body, flags=re.I)
    text = html.unescape(_TAGS.sub(" ", body))
    text = _SPACE.sub(" ", text)
    text = _LINES.sub("\n\n", "\n".join(line.strip() for line in text.splitlines()))
    return title, text.strip()


async def fetch_page_text(url: str, max_chars: int = 6000, timeout: float = 20.0) -> Tuple[str, str, str]:
    """Fetch a public page safely. Returns ``(final_url, title, text)``; raises on failure."""
    current: Optional[str] = url
    headers = {"User-Agent": "Mozilla/5.0 (compatible; AIRAA-research-agent/1.0)", "Accept": "text/html,text/plain;q=0.9"}
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, headers=headers) as client:
        for _ in range(MAX_REDIRECTS + 1):
            await check_public_url(current)
            response = await client.get(current)
            if response.is_redirect and response.headers.get("location"):
                current = urljoin(current, response.headers["location"])
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not any(t in content_type for t in ("text/html", "text/plain", "application/xhtml")):
                raise ValueError(f"Unsupported content type: {content_type or 'unknown'}")
            raw = response.content[:MAX_BYTES].decode(response.encoding or "utf-8", errors="replace")
            title, text = html_to_text(raw) if "html" in content_type else ("", raw)
            return str(response.url), title, text[:max_chars]
    raise ValueError("Too many redirects")
