"""Central configuration. Everything environment-dependent is read here, once."""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv())


# Query parameters that only Prisma understands. libpq (psycopg) rejects unknown ones, so a URL shared with Prisma,
# e.g. ".../postgres?pgbouncer=true", must be cleaned before it is used here.
_PRISMA_ONLY_PARAMS = {"pgbouncer", "connection_limit", "pool_timeout", "schema", "statement_cache_size", "socket_timeout"}


def normalize_database_url(url: str) -> str:
    """Drop Prisma-only query parameters so the same DATABASE_URL works for both Prisma and psycopg."""
    from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

    url = (url or "").strip()
    if "?" not in url:
        return url
    parts = urlsplit(url)
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if k.lower() not in _PRISMA_ONLY_PARAMS]
    return urlunsplit(parts._replace(query=urlencode(kept)))


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
    # Postgres/Supabase connection string (use the pooler URL on Render). Empty = in-memory sessions only.
    database_url: str = field(default_factory=lambda: normalize_database_url(os.getenv("DATABASE_URL", "")))
    db_pool_size: int = field(default_factory=lambda: _int("AIRAA_DB_POOL_SIZE", 5))
    # --- Wallet auth (SIWE) ---------------------------------------------
    # HS256 secret for access tokens. Use the Supabase project's JWT secret to make the same token valid for
    # Supabase RLS. Empty disables wallet sign-in. Must be at least 32 characters.
    jwt_secret: str = field(default_factory=lambda: os.getenv("AIRAA_JWT_SECRET") or os.getenv("SUPABASE_JWT_SECRET", ""))
    access_token_ttl_seconds: int = field(default_factory=lambda: _int("AIRAA_ACCESS_TOKEN_TTL_SECONDS", 900))
    refresh_token_ttl_days: int = field(default_factory=lambda: _int("AIRAA_REFRESH_TOKEN_TTL_DAYS", 30))
    # Hosts (host[:port]) a SIWE message may name as its domain. Defaults to the hosts in ALLOWED_ORIGINS.
    siwe_domains: tuple = field(default_factory=lambda: _list("AIRAA_SIWE_DOMAINS", ""))
    # JSON object {"<chainId>": "<rpc url>"} overriding the built-in public RPCs used for EIP-1271 checks.
    rpc_urls_json: str = field(default_factory=lambda: os.getenv("AIRAA_RPC_URLS", ""))

    # --- Embeddings & retrieval ----------------------------------------
    embedding_model: str = field(default_factory=lambda: os.getenv("AIRAA_EMBEDDING_MODEL", "gemini-embedding-001"))
    embedding_dim: int = 768  # fixed by the vector(768) columns in prisma/migrations/
    memory_top_k: int = field(default_factory=lambda: _int("AIRAA_MEMORY_TOP_K", 5))
    memory_min_similarity: float = field(default_factory=lambda: _float("AIRAA_MEMORY_MIN_SIMILARITY", 0.45))
    memory_dedup_similarity: float = field(default_factory=lambda: _float("AIRAA_MEMORY_DEDUP_SIMILARITY", 0.92))
    memory_half_life_days: float = field(default_factory=lambda: _float("AIRAA_MEMORY_HALF_LIFE_DAYS", 30))
    kb_top_k: int = field(default_factory=lambda: _int("AIRAA_KB_TOP_K", 4))
    kb_min_similarity: float = field(default_factory=lambda: _float("AIRAA_KB_MIN_SIMILARITY", 0.5))
    cache_enabled: bool = field(default_factory=lambda: os.getenv("AIRAA_CACHE_ENABLED", "1") != "0")
    cache_similarity: float = field(default_factory=lambda: _float("AIRAA_CACHE_SIMILARITY", 0.95))
    max_watchlist_items: int = field(default_factory=lambda: _int("AIRAA_MAX_WATCHLIST", 50))

    # --- Sealed storage (Supabase Storage holds ciphertext only) --------
    supabase_url: str = field(default_factory=lambda: os.getenv("SUPABASE_URL", "").rstrip("/"))
    supabase_service_key: str = field(default_factory=lambda: os.getenv("SUPABASE_SERVICE_ROLE_KEY", ""))
    storage_bucket: str = field(default_factory=lambda: os.getenv("AIRAA_STORAGE_BUCKET", "sealed"))
    max_artifact_bytes: int = field(default_factory=lambda: _int("AIRAA_MAX_ARTIFACT_BYTES", 10 * 1024 * 1024))

    # --- Scheduled research (alerts) -----------------------------------
    cron_secret: str = field(default_factory=lambda: os.getenv("AIRAA_CRON_SECRET", ""))
    max_alert_rules: int = field(default_factory=lambda: _int("AIRAA_MAX_ALERT_RULES", 10))
    max_alert_runs_per_day: int = field(default_factory=lambda: _int("AIRAA_MAX_ALERT_RUNS_PER_DAY", 24))
    alert_batch_size: int = field(default_factory=lambda: _int("AIRAA_ALERT_BATCH_SIZE", 5))

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
