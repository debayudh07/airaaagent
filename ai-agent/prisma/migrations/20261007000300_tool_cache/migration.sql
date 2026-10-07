-- Shared semantic cache for tool results. Public market data only: the application never caches
-- wallet-specific tools (Etherscan) here. Server-only: RLS enabled with no policies.
-- Idempotent.

create table if not exists tool_cache (
    key_hash     text primary key,            -- sha256(tool | params_hash | normalised query)
    tool         text not null,
    params_hash  text not null,               -- sha256 of the tool arguments minus the free-text fields
    query_text   text not null,               -- the free text that was embedded
    embedding    vector(768),
    result       jsonb not null,
    created_at   timestamptz not null default now(),
    expires_at   timestamptz not null,
    hits         integer not null default 0
);
create index if not exists tool_cache_expires_idx on tool_cache (expires_at);
create index if not exists tool_cache_lookup_idx on tool_cache (tool, params_hash);
create index if not exists tool_cache_embedding_idx
    on tool_cache using hnsw (embedding vector_cosine_ops) where embedding is not null;

-- Nearest live entry for the same tool + same structured arguments.
create or replace function match_tool_cache(
    p_tool text, p_params_hash text, p_embedding vector(768), p_threshold real
) returns table (key_hash text, result jsonb, created_at timestamptz, similarity real)
language sql stable as $$
    select c.key_hash, c.result, c.created_at, (1 - (c.embedding <=> p_embedding))::real as similarity
    from tool_cache c
    where c.tool = p_tool
      and c.params_hash = p_params_hash
      and c.embedding is not null
      and c.expires_at > now()
      and 1 - (c.embedding <=> p_embedding) >= p_threshold
    order by c.embedding <=> p_embedding
    limit 1
$$;

alter table tool_cache enable row level security;
