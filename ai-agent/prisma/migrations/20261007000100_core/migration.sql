-- AIRAA phase 1+2 core schema: wallets, auth sessions, conversations, messages.
-- Applied with:  npx prisma migrate deploy   (or  python -m airaa.db.migrate ,  or paste into the Supabase SQL editor)
-- Idempotent: safe to re-run.

create extension if not exists vector;   -- used from migration 002 onward

-- ---------------------------------------------------------------- wallets
create table if not exists wallets (
    id          uuid primary key default gen_random_uuid(),
    address     text not null unique check (address ~ '^0x[a-f0-9]{40}$'),   -- always stored lower-case
    first_seen  timestamptz not null default now(),
    last_seen   timestamptz not null default now(),
    plan        text not null default 'free',
    settings    jsonb not null default '{"memory_enabled": true}'::jsonb,
    vault_meta  jsonb not null default '{}'::jsonb
);

-- ---------------------------------------------------------------- SIWE auth
create table if not exists auth_nonces (
    nonce       text primary key,
    expires_at  timestamptz not null,
    used_at     timestamptz
);
create index if not exists auth_nonces_expires_idx on auth_nonces (expires_at);

create table if not exists auth_sessions (
    id            uuid primary key default gen_random_uuid(),
    wallet_id     uuid not null references wallets(id) on delete cascade,
    family_id     uuid not null default gen_random_uuid(),   -- refresh-token rotation family
    refresh_hash  text not null,                              -- sha256 of the current refresh token
    user_agent    text,
    ip_hash       text,
    created_at    timestamptz not null default now(),
    expires_at    timestamptz not null,
    revoked_at    timestamptz
);
create index if not exists auth_sessions_wallet_idx on auth_sessions (wallet_id);
create index if not exists auth_sessions_refresh_idx on auth_sessions (refresh_hash);

-- ---------------------------------------------------------------- conversations
-- id is text, not uuid: it is the existing client-facing session id (^[A-Za-z0-9_-]{8,100}$).
-- wallet_id is null for guest conversations until they are claimed by a connected wallet.
create table if not exists conversations (
    id             text primary key check (id ~ '^[A-Za-z0-9_-]{8,100}$'),
    wallet_id      uuid references wallets(id) on delete cascade,
    title          text,
    summary        text,
    context        jsonb not null default '{}'::jsonb,        -- SessionManager.research_context
    message_count  integer not null default 0,
    created_at     timestamptz not null default now(),
    last_activity  timestamptz not null default now()
);
create index if not exists conversations_wallet_idx on conversations (wallet_id, last_activity desc);

create table if not exists messages (
    id               bigint generated always as identity primary key,
    conversation_id  text not null references conversations(id) on delete cascade,
    role             text not null check (role in ('human', 'ai')),
    content          text not null,
    extra            jsonb not null default '{}'::jsonb,       -- additional_kwargs: timestamp, research_data
    created_at       timestamptz not null default now()
);
create index if not exists messages_conv_idx on messages (conversation_id, id);

-- ---------------------------------------------------------------- RLS
-- The Flask backend connects with a role that bypasses RLS (service role / postgres) and enforces
-- wallet scoping in its queries. RLS is defence in depth for anything reached with a user JWT
-- (e.g. direct Supabase client access): rows are visible only to the wallet in the token's `sub`.
alter table wallets        enable row level security;
alter table auth_sessions  enable row level security;
alter table auth_nonces    enable row level security;   -- no policy: server only
alter table conversations  enable row level security;
alter table messages       enable row level security;

drop policy if exists wallets_self on wallets;
create policy wallets_self on wallets
    for select using (id = (auth.jwt() ->> 'sub')::uuid);

drop policy if exists auth_sessions_self on auth_sessions;
create policy auth_sessions_self on auth_sessions
    for select using (wallet_id = (auth.jwt() ->> 'sub')::uuid);

drop policy if exists conversations_owner on conversations;
create policy conversations_owner on conversations
    for all using (wallet_id = (auth.jwt() ->> 'sub')::uuid)
    with check (wallet_id = (auth.jwt() ->> 'sub')::uuid);

drop policy if exists messages_owner on messages;
create policy messages_owner on messages
    for all using (
        exists (select 1 from conversations c
                where c.id = messages.conversation_id
                  and c.wallet_id = (auth.jwt() ->> 'sub')::uuid)
    );

-- Prisma's own bookkeeping table lives in `public`, which Supabase exposes through its REST API. It holds nothing
-- sensitive, but with RLS on and no policy it is closed to the anon/authenticated keys like everything else here.
-- (It exists by the time this file runs: Prisma creates it before applying the first migration.)
alter table if exists public._prisma_migrations enable row level security;
