-- Long-term chat memory. Embeddings are vector(768) (Gemini embedding with output_dimensionality=768);
-- changing the dimension needs a new migration that re-embeds.
-- Idempotent.

create table if not exists memories (
    id               uuid primary key default gen_random_uuid(),
    wallet_id        uuid not null references wallets(id) on delete cascade,
    conversation_id  text references conversations(id) on delete set null,
    kind             text not null check (kind in ('fact', 'preference', 'finding', 'summary')),
    content          text not null check (length(content) between 1 and 2000),
    importance       real not null default 0.5 check (importance between 0 and 1),
    pinned           boolean not null default false,
    embedding        vector(768) not null,
    created_at       timestamptz not null default now(),
    last_accessed    timestamptz,
    access_count     integer not null default 0,
    expires_at       timestamptz
);

-- No HNSW index on purpose: every query is filtered by wallet_id, a wallet holds hundreds of rows at most,
-- and an unfiltered ANN index would post-filter its candidates (returning too few rows for small wallets).
-- The btree below narrows to one wallet, then distance is computed exactly.
create index if not exists memories_wallet_idx on memories (wallet_id, created_at desc);

create or replace function match_memories(
    p_wallet uuid, p_embedding vector(768), p_k integer default 8, p_min_similarity real default 0.0
) returns table (
    id uuid, kind text, content text, importance real, pinned boolean,
    created_at timestamptz, last_accessed timestamptz, similarity real
) language sql stable as $$
    select m.id, m.kind, m.content, m.importance, m.pinned, m.created_at, m.last_accessed,
           (1 - (m.embedding <=> p_embedding))::real as similarity
    from memories m
    where m.wallet_id = p_wallet
      and (m.expires_at is null or m.expires_at > now())
      and 1 - (m.embedding <=> p_embedding) >= p_min_similarity
    order by m.embedding <=> p_embedding
    limit p_k
$$;

alter table memories enable row level security;
drop policy if exists memories_owner on memories;
create policy memories_owner on memories
    for all using (wallet_id = (auth.jwt() ->> 'sub')::uuid)
    with check (wallet_id = (auth.jwt() ->> 'sub')::uuid);
