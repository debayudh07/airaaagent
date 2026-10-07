"""Apply ``prisma/migrations/*/migration.sql`` in order, once each, without needing Node.

    python -m airaa.db.migrate            # uses DATABASE_URL

These are the same files ``npx prisma migrate deploy`` applies (see ``package.json``); use either tool, not both on the
same database, because they keep separate books (``public.schema_migrations`` here, ``_prisma_migrations`` there).
Each file runs in its own transaction, so a failure leaves the database at the previous migration. The SQL is also
idempotent, so pasting a file into the Supabase SQL editor is fine too.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import List

import psycopg

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "prisma" / "migrations"
logger = logging.getLogger(__name__)


def migration_files() -> List[Path]:
    return sorted(MIGRATIONS_DIR.glob("*/migration.sql"))


def apply_all(database_url: str) -> List[str]:
    """Run pending migrations. Returns the names applied this call."""
    applied: List[str] = []
    with psycopg.connect(database_url, autocommit=True, prepare_threshold=None) as conn:
        conn.execute("create table if not exists public.schema_migrations (name text primary key, applied_at timestamptz not null default now())")
        done = {row[0] for row in conn.execute("select name from public.schema_migrations").fetchall()}
        for path in migration_files():
            name = path.parent.name
            if name in done:
                continue
            logger.info("Applying %s", name)
            with conn.transaction():
                conn.execute(path.read_text(encoding="utf-8"))
                conn.execute("insert into public.schema_migrations (name) values (%s)", (name,))
            applied.append(name)
    return applied


def main() -> int:
    from ..config import get_settings

    logging.basicConfig(level="INFO", format="%(message)s")
    url = get_settings().database_url
    if not url:
        print("DATABASE_URL is not set", file=sys.stderr)
        return 1
    applied = apply_all(url)
    print("Applied: " + ", ".join(applied) if applied else "Database is up to date")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
