-- Per-wallet personalisation context: watchlist and portfolio snapshots.
-- Idempotent.

create table if not exists watchlist (
    id           uuid primary key default gen_random_uuid(),
    wallet_id    uuid not null references wallets(id) on delete cascade,
    entity_type  text not null check (entity_type in ('token', 'protocol', 'chain')),
    entity_id    text not null check (length(entity_id) between 1 and 80),   -- lower-case symbol / slug / chain name
    note         text check (note is null or length(note) <= 500),
    embedding    vector(768),
    added_at     timestamptz not null default now(),
    unique (wallet_id, entity_type, entity_id)
);
create index if not exists watchlist_wallet_idx on watchlist (wallet_id, added_at desc);

create table if not exists portfolio_snapshots (
    id          uuid primary key default gen_random_uuid(),
    wallet_id   uuid not null references wallets(id) on delete cascade,
    chain       text not null,
    fetched_at  timestamptz not null default now(),
    holdings    jsonb not null default '{}'::jsonb,
    summary     text not null,
    embedding   vector(768)
);
create index if not exists portfolio_wallet_idx on portfolio_snapshots (wallet_id, fetched_at desc);

create or replace function match_watchlist(
    p_wallet uuid, p_embedding vector(768), p_k integer default 5, p_min_similarity real default 0.0
) returns table (entity_type text, entity_id text, note text, similarity real)
language sql stable as $$
    select w.entity_type, w.entity_id, w.note, (1 - (w.embedding <=> p_embedding))::real as similarity
    from watchlist w
    where w.wallet_id = p_wallet and w.embedding is not null
      and 1 - (w.embedding <=> p_embedding) >= p_min_similarity
    order by w.embedding <=> p_embedding
    limit p_k
$$;

alter table watchlist           enable row level security;
alter table portfolio_snapshots enable row level security;
drop policy if exists watchlist_owner on watchlist;
create policy watchlist_owner on watchlist
    for all using (wallet_id = (auth.jwt() ->> 'sub')::uuid)
    with check (wallet_id = (auth.jwt() ->> 'sub')::uuid);
drop policy if exists portfolio_owner on portfolio_snapshots;
create policy portfolio_owner on portfolio_snapshots
    for select using (wallet_id = (auth.jwt() ->> 'sub')::uuid);
