-- Scheduled research ("alerts") and the per-wallet inbox their results land in. Idempotent.

create table if not exists alert_rules (
    id                uuid primary key default gen_random_uuid(),
    wallet_id         uuid not null references wallets(id) on delete cascade,
    name              text not null check (length(name) between 1 and 80),
    query_text        text not null check (length(query_text) between 1 and 1000),
    condition_text    text check (condition_text is null or length(condition_text) <= 300),  -- null = always notify
    interval_minutes  integer not null default 1440 check (interval_minutes >= 15),
    enabled           boolean not null default true,
    next_run_at       timestamptz not null default now(),
    last_run_at       timestamptz,
    last_error        text,
    run_day           date,
    runs_today        integer not null default 0,
    created_at        timestamptz not null default now()
);
create index if not exists alert_rules_due_idx on alert_rules (next_run_at) where enabled;
create index if not exists alert_rules_wallet_idx on alert_rules (wallet_id);

create table if not exists inbox (
    id             uuid primary key default gen_random_uuid(),
    wallet_id      uuid not null references wallets(id) on delete cascade,
    rule_id        uuid references alert_rules(id) on delete set null,
    title          text not null,
    summary        text not null,
    research_data  jsonb,
    created_at     timestamptz not null default now(),
    read_at        timestamptz
);
create index if not exists inbox_wallet_idx on inbox (wallet_id, created_at desc);

alter table alert_rules enable row level security;
alter table inbox       enable row level security;
drop policy if exists alert_rules_owner on alert_rules;
create policy alert_rules_owner on alert_rules
    for all using (wallet_id = (auth.jwt() ->> 'sub')::uuid)
    with check (wallet_id = (auth.jwt() ->> 'sub')::uuid);
drop policy if exists inbox_owner on inbox;
create policy inbox_owner on inbox
    for all using (wallet_id = (auth.jwt() ->> 'sub')::uuid)
    with check (wallet_id = (auth.jwt() ->> 'sub')::uuid);
