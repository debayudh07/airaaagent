import 'dotenv/config';
import { defineConfig } from 'prisma/config';

/**
 * Prisma is used here only to apply the hand-written SQL in prisma/migrations (pgvector, RLS policies, SQL functions
 * and generated columns are beyond what `prisma db push` models, which is why this is `migrate deploy`, not `db push`).
 *
 * Migrations need a connection that supports DDL and advisory locks, which Supabase's *transaction* pooler (port 6543,
 * what the app uses) does not. So the URL is, in order:
 *   1. DIRECT_URL if set (Supabase "Direct connection" or "Session pooler" string);
 *   2. otherwise DATABASE_URL moved to the session pooler: same host, port 5432, Prisma-only query params removed.
 */
function migrationUrl(): string {
  const direct = process.env.DIRECT_URL?.trim();
  if (direct) return direct;
  const raw = process.env.DATABASE_URL?.trim();
  if (!raw) throw new Error('Set DATABASE_URL (or DIRECT_URL) in ai-agent/.env');
  const url = new URL(raw);
  if (url.hostname.endsWith('.pooler.supabase.com') && url.port === '6543') url.port = '5432';
  for (const key of ['pgbouncer', 'connection_limit', 'pool_timeout']) url.searchParams.delete(key);
  return url.toString();
}

export default defineConfig({
  schema: 'prisma/schema.prisma',
  migrations: { path: 'prisma/migrations' },
  datasource: { url: migrationUrl() },
});
