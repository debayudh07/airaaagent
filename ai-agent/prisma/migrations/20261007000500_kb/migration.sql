-- Protocol knowledge base (shared RAG corpus): documents, chunks, hybrid (vector + full-text) search.
-- Written by the ingest script only; clients may read. Idempotent.

create table if not exists kb_documents (
    id            uuid primary key default gen_random_uuid(),
    source        text not null,               -- e.g. 'api-docs', 'protocol-docs'
    url           text not null unique,        -- canonical locator; also the citation target
    title         text not null,
    content_hash  text not null,               -- sha256 of the source text; unchanged = skip re-embedding
    fetched_at    timestamptz not null default now()
);

create table if not exists kb_chunks (
    id           uuid primary key default gen_random_uuid(),
    document_id  uuid not null references kb_documents(id) on delete cascade,
    chunk_index  integer not null,
    content      text not null,
    content_tsv  tsvector generated always as (to_tsvector('english', content)) stored,
    embedding    vector(768) not null,
    metadata     jsonb not null default '{}'::jsonb,
    unique (document_id, chunk_index)
);
create index if not exists kb_chunks_embedding_idx on kb_chunks using hnsw (embedding vector_cosine_ops);
create index if not exists kb_chunks_tsv_idx on kb_chunks using gin (content_tsv);

-- Hybrid retrieval: reciprocal-rank fusion of the vector ranking and the full-text ranking.
create or replace function match_kb(
    p_embedding vector(768), p_query text, p_k integer default 4
) returns table (
    id uuid, content text, metadata jsonb, title text, url text, similarity real, score double precision
) language sql stable as $$
    with v as (
        select c.id, row_number() over (order by c.embedding <=> p_embedding) as r
        from kb_chunks c order by c.embedding <=> p_embedding limit 20
    ), t as (
        select c.id, row_number() over (order by ts_rank_cd(c.content_tsv, q) desc) as r
        from kb_chunks c, websearch_to_tsquery('english', coalesce(p_query, '')) q
        where c.content_tsv @@ q
        order by ts_rank_cd(c.content_tsv, q) desc limit 20
    ), fused as (
        select coalesce(v.id, t.id) as id,
               coalesce(1.0 / (60 + v.r), 0) + coalesce(1.0 / (60 + t.r), 0) as score
        from v full join t on v.id = t.id
    )
    select c.id, c.content, c.metadata, d.title, d.url,
           (1 - (c.embedding <=> p_embedding))::real as similarity, f.score
    from fused f
    join kb_chunks c on c.id = f.id
    join kb_documents d on d.id = c.document_id
    order by f.score desc
    limit p_k
$$;

alter table kb_documents enable row level security;
alter table kb_chunks    enable row level security;
drop policy if exists kb_documents_read on kb_documents;
create policy kb_documents_read on kb_documents for select using (true);
drop policy if exists kb_chunks_read on kb_chunks;
create policy kb_chunks_read on kb_chunks for select using (true);
