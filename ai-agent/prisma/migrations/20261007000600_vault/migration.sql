-- Client-side encrypted ("sealed") storage: wrapped vault keys, artifact metadata, shares.
-- The server only ever holds ciphertext and wrapped keys. Idempotent.

-- One row per way of unlocking the user's data-encryption key (DEK). The DEK itself never leaves the
-- browser unwrapped; losing every wrapper loses the data, so the client creates several.
create table if not exists vault_keys (
    id           uuid primary key default gen_random_uuid(),
    wallet_id    uuid not null references wallets(id) on delete cascade,
    wrapper_type text not null check (wrapper_type in ('signature', 'passphrase', 'recovery')),
    wrapped_dek  bytea not null,
    kdf          jsonb not null default '{}'::jsonb,    -- non-secret parameters: salt, iterations, vault message
    created_at   timestamptz not null default now(),
    unique (wallet_id, wrapper_type)
);

-- Ciphertext blobs when Supabase Storage is not configured (server-only; RLS on, no policies).
create table if not exists artifact_blobs (
    path        text primary key,
    data        bytea not null,
    created_at  timestamptz not null default now()
);
alter table artifact_blobs enable row level security;

-- Each artifact is encrypted with its own random content key (CEK); the CEK is wrapped by the DEK.
-- That lets one artifact be shared (CEK re-wrapped for the recipient) without exposing the DEK.
create table if not exists artifacts (
    id               uuid primary key default gen_random_uuid(),
    wallet_id        uuid not null references wallets(id) on delete cascade,
    storage_path     text not null,
    size_bytes       integer not null check (size_bytes > 0),
    enc_alg          text not null default 'A256GCM',
    wrapped_cek      bytea not null,
    meta_enc         bytea,                              -- title / tags / mime, encrypted client-side
    index_summary    text,                               -- OPT-IN plaintext summary the user chose to expose for search
    index_embedding  vector(768),
    created_at       timestamptz not null default now()
);
create index if not exists artifacts_wallet_idx on artifacts (wallet_id, created_at desc);

-- Shares of a conversation (plaintext tier) or a sealed artifact (link shares only).
create table if not exists shares (
    id                    uuid primary key default gen_random_uuid(),
    owner_wallet_id       uuid not null references wallets(id) on delete cascade,
    resource_type         text not null check (resource_type in ('conversation', 'artifact')),
    resource_id           text not null,
    mode                  text not null check (mode in ('wallet', 'link')),
    recipient_address     text check (recipient_address is null or recipient_address ~ '^0x[a-f0-9]{40}$'),
    token_hash            text unique,                   -- sha256 of the link token; null for wallet shares
    wrapped_key           bytea,                         -- artifact CEK wrapped by the link secret (URL fragment, never sent here)
    redact_research_data  boolean not null default false,
    created_at            timestamptz not null default now(),
    expires_at            timestamptz,
    revoked_at            timestamptz,
    check ((mode = 'wallet' and recipient_address is not null and token_hash is null)
        or (mode = 'link' and token_hash is not null)),
    check (resource_type = 'conversation' or mode = 'link')   -- wallet-to-wallet artifact sharing is not supported yet
);
create index if not exists shares_owner_idx on shares (owner_wallet_id, created_at desc);
create index if not exists shares_recipient_idx on shares (recipient_address) where recipient_address is not null;

alter table vault_keys enable row level security;
alter table artifacts  enable row level security;
alter table shares     enable row level security;
drop policy if exists vault_keys_owner on vault_keys;
create policy vault_keys_owner on vault_keys
    for all using (wallet_id = (auth.jwt() ->> 'sub')::uuid)
    with check (wallet_id = (auth.jwt() ->> 'sub')::uuid);
drop policy if exists artifacts_owner on artifacts;
create policy artifacts_owner on artifacts
    for all using (wallet_id = (auth.jwt() ->> 'sub')::uuid)
    with check (wallet_id = (auth.jwt() ->> 'sub')::uuid);
drop policy if exists shares_owner on shares;
create policy shares_owner on shares
    for all using (owner_wallet_id = (auth.jwt() ->> 'sub')::uuid)
    with check (owner_wallet_id = (auth.jwt() ->> 'sub')::uuid);

create or replace function match_artifacts(
    p_wallet uuid, p_embedding vector(768), p_k integer default 10, p_min_similarity real default 0.0
) returns table (id uuid, index_summary text, created_at timestamptz, similarity real)
language sql stable as $$
    select a.id, a.index_summary, a.created_at, (1 - (a.index_embedding <=> p_embedding))::real
    from artifacts a
    where a.wallet_id = p_wallet and a.index_embedding is not null
      and 1 - (a.index_embedding <=> p_embedding) >= p_min_similarity
    order by a.index_embedding <=> p_embedding
    limit p_k
$$;

-- Private bucket for the ciphertext objects (Supabase only; plain Postgres has no storage schema).
do $$
begin
    if to_regclass('storage.buckets') is not null then
        insert into storage.buckets (id, name, public) values ('sealed', 'sealed', false)
        on conflict (id) do nothing;
    end if;
end $$;
