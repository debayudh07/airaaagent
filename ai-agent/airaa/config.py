"""Central configuration. Everything environment-dependent is read here, once."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())


def _float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def _list(name: str, default: str) -> tuple:
    return tuple(x.strip() for x in os.getenv(name, default).split(",") if x.strip())


def _int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass(frozen=True)
class Settings:
    # --- API keys -------------------------------------------------------
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY", ""))
    coinmarketcap_api_key: str = field(default_factory=lambda: os.getenv("COINMARKETCAP_API_KEY", ""))
    etherscan_api_key: str = field(default_factory=lambda: os.getenv("ETHERSCAN_API_KEY", ""))
    dune_api_key: str = field(default_factory=lambda: os.getenv("DUNE_API_KEY", ""))
    coingecko_api_key: str = field(default_factory=lambda: os.getenv("COINGECKO_API_KEY", ""))  # optional demo key

    # --- Models ---------------------------------------------------------
    # Synthesis writes the user-facing answer; the planner/reflector make
    # short structured decisions, so a cheaper Flash-Lite model is enough.
    synthesis_model: str = field(default_factory=lambda: os.getenv("AIRAA_SYNTHESIS_MODEL", "gemini-3.8-flash"))
    planner_model: str = field(default_factory=lambda: os.getenv("AIRAA_PLANNER_MODEL", "gemini-3.5-flash-lite"))
    # Tried in order when the primary returns 503/429 (quotas are per model).
    synthesis_fallbacks: tuple = field(default_factory=lambda: _list("AIRAA_SYNTHESIS_FALLBACKS", "gemini-3.6-flash,gemini-3.5-flash"))
    planner_fallbacks: tuple = field(default_factory=lambda: _list("AIRAA_PLANNER_FALLBACKS", "gemini-3.1-flash-lite,gemini-3.5-flash"))
    # Reads web pages via Gemini's URL context tool (works on the free tier).
    reader_model: str = field(default_factory=lambda: os.getenv("AIRAA_READER_MODEL", "gemini-3.5-flash-lite"))
    max_output_tokens: int = field(default_factory=lambda: _int("AIRAA_MAX_OUTPUT_TOKENS", 4000))
    max_charts: int = field(default_factory=lambda: _int("AIRAA_MAX_CHARTS", 3))

    # --- Agent behaviour ------------------------------------------------
    tool_timeout_seconds: float = field(default_factory=lambda: _float("TOOL_TIMEOUT_SECONDS", 40))
    planner_timeout_seconds: float = field(default_factory=lambda: _float("PLANNER_TIMEOUT_SECONDS", 15))
    tool_retries: int = field(default_factory=lambda: _int("AIRAA_TOOL_RETRIES", 1))
    max_followup_rounds: int = field(default_factory=lambda: _int("AIRAA_MAX_FOLLOWUP_ROUNDS", 1))
    reflect_below_completeness: float = field(default_factory=lambda: _float("AIRAA_REFLECT_BELOW", 50))
    history_messages: int = field(default_factory=lambda: _int("AIRAA_HISTORY_MESSAGES", 6))

    # --- Sessions / API -------------------------------------------------
    max_sessions: int = field(default_factory=lambda: _int("AIRAA_MAX_SESSIONS", 200))
    session_ttl_hours: int = field(default_factory=lambda: _int("AIRAA_SESSION_TTL_HOURS", 24))
    allowed_origins: str = field(default_factory=lambda: os.getenv("ALLOWED_ORIGINS", "*"))
    rate_limit_per_minute: int = field(default_factory=lambda: _int("AIRAA_RATE_LIMIT_PER_MINUTE", 20))
    max_query_chars: int = field(default_factory=lambda: _int("AIRAA_MAX_QUERY_CHARS", 1000))
    admin_token: str = field(default_factory=lambda: os.getenv("ADMIN_TOKEN", ""))

    def configured_sources(self) -> dict[str, bool]:
        """Which upstream integrations have credentials (DefiLlama needs none)."""
        return {
            "gemini": bool(self.gemini_api_key),
            "coinmarketcap": bool(self.coinmarketcap_api_key),
            "etherscan": bool(self.etherscan_api_key),
            "dune": bool(self.dune_api_key),
            "defillama": True,
            "coingecko": True,
            "dexscreener": True,
            "web_search": True,
            "news": True,
        }


def get_settings() -> Settings:
    """Settings are cheap to build and re-read the environment, which keeps tests simple."""
    return Settings()


# Module-level handle for code that does not need per-call overrides.
settings = get_settings()
