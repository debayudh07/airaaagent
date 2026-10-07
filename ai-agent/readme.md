# AIRAA agent (backend)

Flask API around a tool-using research agent for Web3 questions. It plans which data sources to query,
fetches them in parallel, checks for gaps, and writes an answer grounded in the data it actually retrieved.

## How a question is answered

```
question ──► greeting? ──yes──► canned reply (no LLM, no data calls)
                │ no
                ▼
        PLAN   gemini-3.5-flash-lite, structured output: which tools + which coins/protocols/chain
                │   (falls back to keyword rules if the model is down or slow)
                ▼
        GATHER tools run in parallel, 40s timeout each, one retry on timeouts / 429 / 5xx
                │
                ▼
        REFLECT only if a tool failed: "would one more round help?" (max 1 extra round)
                │
                ▼
     SYNTHESISE gemini-3.8-flash streams the answer from a "verified data" block;
                if the model is unavailable, the retrieved data is returned instead
```

Every result carries `tool_trace` (per-tool timing, attempts, errors), the plan, and `data_quality_score`, which is the
percentage of attempted sources that responded. Failed sources are named in the answer footer.

## Layout

```
ai-agent/
├── app.py                 WSGI entry point (gunicorn app:app)
├── main.py                CLI: python main.py "price of ETH"
├── airaa/
│   ├── config.py          all environment-driven settings (models, timeouts, limits)
│   ├── schemas.py         ResearchRequest + the LLM's structured outputs (Plan, FollowUp)
│   ├── http.py            per-run httpx client (safe across Flask's per-request event loops)
│   ├── memory.py          conversation sessions: in-process cache, write-through to Postgres when configured
│   ├── services.py        wires the optional database-backed features from settings
│   ├── auth/              wallet sign-in: SIWE (EIP-4361) parsing/verification, EIP-1271, access + refresh tokens
│   ├── embeddings.py      Gemini embeddings (768-d) shared by everything below
│   ├── memory_store.py    long-term memory: extract -> embed -> dedupe; recall ranked by similarity/recency/importance
│   ├── cache/             semantic cache for public tool results
│   ├── kb/                protocol knowledge base: chunking, ingest CLI, hybrid retrieval
│   ├── context_service.py watchlist + on-chain portfolio snapshots
│   ├── retrieval.py       what the agent pulls in before planning (memory, watchlist, docs) and saves afterwards
│   ├── vault/             sealed (client-side encrypted) files and sharing
│   ├── alerts/            scheduled research runner and inbox
│   ├── db/                pool, repositories (one per area) and the migration runner
│   ├── greeting.py        small-talk detection
│   ├── tools/             coinmarketcap, defillama, dune, etherscan (+ TOOL_CATALOG for the planner)
│   ├── agent/
│   │   ├── core.py        Web3ResearchAgent: the plan -> gather -> reflect -> synthesise loop
│   │   ├── planner.py     LLM planner + rule-based fallback + reflection
│   │   ├── executor.py    parallel tool runner (timeouts, retries, trace)
│   │   ├── merge.py       tool results -> merged_data
│   │   ├── context.py     merged_data -> the text the model sees
│   │   ├── prompts.py     system prompts
│   │   └── llm.py         Gemini factories
│   └── api/               Flask app factory, routes, validation, rate limiting
├── prisma/                migrations/ = the SQL schema (Supabase Postgres + pgvector), applied by Prisma or by airaa.db.migrate
└── tests/                 pytest suite; tests/integration runs against a real Postgres; tests/manual holds old live-API scripts
```

## Run it

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                  # add your keys
python app.py                                         # http://localhost:8000
python main.py "compare BTC and SOL"                  # or use the CLI
```

Only `GEMINI_API_KEY` is required. Each other key enables one source; the agent reports a missing key as an
unavailable source instead of failing. DefiLlama needs no key.

## Persistence and wallet features (optional)

Everything in this section switches on with `DATABASE_URL`; without it the app runs exactly as before. Each feature
also has its own prerequisite, and `GET /api/health` reports what is on under `features`.

| Feature | Needs | What it does |
|---|---|---|
| Persistent conversations | `DATABASE_URL` | history survives restarts and is shared across workers |
| Wallet sign-in | + `AIRAA_JWT_SECRET` | SIWE login (EOAs and EIP-1271 smart wallets); conversations become private to the wallet |
| Long-term memory | + `GEMINI_API_KEY` | the agent remembers durable facts and preferences per wallet and recalls them next time |
| Watchlist and portfolio | `DATABASE_URL` (+ `ETHERSCAN_API_KEY` for snapshots) | answers are personalised to what the wallet follows and holds |
| Knowledge base (RAG) | + `GEMINI_API_KEY` | protocol and API docs retrieved with citations |
| Semantic tool cache | `DATABASE_URL` | public market data is reused for near-identical questions within a short TTL |
| Sealed storage | `DATABASE_URL` | files encrypted in the browser; the server stores ciphertext and wrapped keys only |
| Sharing | sealed storage / conversations | revocable links (and wallet-to-wallet for conversations) |
| Alerts | `AIRAA_CRON_SECRET` + a scheduler | scheduled research whose results land in a wallet inbox |

### Set it up

```bash
# 1. Supabase project -> Connect -> Transaction pooler string -> DATABASE_URL in .env
# 2. a signing secret:  python -c "import secrets; print(secrets.token_urlsafe(48))"  -> AIRAA_JWT_SECRET
npm install && npx prisma migrate deploy       # creates the schema (Prisma applies prisma/migrations/*; check with `npx prisma migrate status`)
# ...or without Node:  python -m airaa.db.migrate   (same files; use one tool per database, not both)
python -m airaa.kb.ingest --default              # optional: load the bundled DefiLlama API docs into the knowledge base
python -m airaa.kb.ingest https://docs.aave.com/ # ...or any page / .md / .txt / OpenAPI .json
```

In production set `ALLOWED_ORIGINS` to your frontend origin: the refresh-token cookie only works cross-site with
explicit origins. Run alerts by pointing a scheduler at `POST /api/internal/alerts/run` with the `X-Cron-Secret`
header (`.github/workflows/alerts.yml` does this every 15 minutes).

### Design notes

- **Identity.** Send `Authorization: Bearer <access token>` to act as a wallet; omit it to stay a guest. A bad token is a
  401, never a silent downgrade. Access tokens last 15 minutes; the refresh token is an httpOnly cookie scoped to
  `/api/auth`, rotated on every use. Presenting an already-rotated token revokes the whole session family.
- **Privacy tiers.** Chat history, memories, watchlist and tool cache are readable by the server (it needs the text to
  embed it and build prompts) and isolated per wallet by queries plus row-level security. Sealed files are different: the
  browser encrypts with AES-256-GCM, the key is wrapped by a wallet-signature-derived key, a passphrase and a recovery key,
  and the server cannot read them or search inside them. An optional summary can be exposed on purpose for search.
- **Cache safety.** Only public tools are cached, never Etherscan. Structured arguments (coins, protocols, chain) must match
  exactly; only the free-text question is matched semantically, so "ETH price" is never answered with BTC data.
- **Memory.** Extraction runs after the answer is sent, in a background thread. Automated alert runs read memory but never write it.
  Users can pause memory, edit or delete entries, export everything, or erase their account.
- **Why `migrate deploy`, not `db push`.** The schema uses pgvector, RLS policies, SQL functions and generated columns, which `schema.prisma` does not model; `db push` would try to make the database match a model-less schema. `migrate deploy` just applies the SQL files, and Prisma records them in `_prisma_migrations`.
- **Known limits.** Smart wallets that are not deployed yet (ERC-6492 signatures) cannot sign in. Sealed files can be shared
  by link only (wallet-to-wallet needs recipient key registration). A revoked link stops working, but a recipient who already
  decrypted a file keeps what they saw.

## Models

| Role | Default | Env override |
|---|---|---|
| Answer synthesis | `gemini-3.8-flash` | `AIRAA_SYNTHESIS_MODEL` |
| Planning and reflection | `gemini-3.5-flash-lite` | `AIRAA_PLANNER_MODEL` |

Google shut down `gemini-2.0-flash` on 2026-06-01. Check [the Gemini model list](https://ai.google.dev/gemini-api/docs/models)
before pinning a model; both defaults are overridable without a code change.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | status, model names, which sources have credentials |
| GET | `/api/tools` | tool catalog |
| POST | `/api/research` | run a question, return JSON |
| POST | `/api/research/stream` | same, as Server-Sent Events |
| GET | `/api/conversation/<id>` | history for a session |
| DELETE | `/api/conversation/<id>` | forget a session |
| GET | `/api/sessions` | operator listing; returns 404 unless `ADMIN_TOKEN` is set, then needs `X-Admin-Token` |

With persistence enabled (everything below needs a signed-in wallet unless marked public):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/auth/nonce` | start sign-in (public) |
| POST | `/api/auth/verify` | `{message, signature}` -> access token + refresh cookie (public) |
| POST | `/api/auth/refresh`, `/api/auth/logout` | rotate / end the session (cookie) |
| GET | `/api/auth/me`, `/api/me` | identity, settings, counts |
| PATCH | `/api/me/settings` | `{memory_enabled}` |
| GET | `/api/me/export` | everything held about the wallet, as JSON |
| DELETE | `/api/me` | erase the account (`{"confirm": "DELETE"}`) |
| GET, POST | `/api/conversations`, `/api/conversations/claim` | list; claim the guest conversation in use |
| GET, POST, PATCH, DELETE | `/api/memories[/<id>]` | memory dashboard |
| GET, POST, DELETE | `/api/watchlist[/<id>]` | watchlist |
| GET, POST | `/api/portfolio`, `/api/portfolio/refresh` | on-chain snapshot |
| GET, PUT, DELETE | `/api/vault`, `/api/vault/keys/<type>` | wrapped vault keys (`signature`, `passphrase`, `recovery`) |
| GET, POST, DELETE | `/api/artifacts[/<id>[/blob]]`, `/api/artifacts/search` | sealed files |
| GET, POST, DELETE | `/api/shares[/<id>]`, `/api/shares/received` | manage shares |
| GET | `/api/share/<token>` | open a link share (public) |
| GET | `/api/shared/conversation/<id>` | open a conversation shared with your wallet |
| GET, POST, PATCH, DELETE | `/api/alerts[/<id>]` | alert rules |
| GET, POST, DELETE | `/api/inbox[/<id>]`, `/api/inbox/read`, `/api/inbox/unread-count` | alert results |
| POST | `/api/internal/alerts/run` | scheduler hook (`X-Cron-Secret`) |

Request body for both research endpoints:

```json
{ "query": "TVL of Aave", "address": "0x...", "time_range": "7d", "session_id": "web-1700000000-abc123" }
```

`query` is required (max 1000 chars); `address` must be a 0x address; `time_range` is one of `1d 7d 30d 90d 1y`;
`session_id` is 8-100 chars of letters, digits, `-`, `_`. Invalid input gets a 400, and more than
`AIRAA_RATE_LIMIT_PER_MINUTE` research requests per client per minute gets a 429 with `Retry-After`.

Stream events (`data: {json}` lines): `status`, `plan`, `tool_start`, `tool_retry`, `tool_end`, `followup`, `token`, then `result`
(or `error`). Closing the connection stops the run.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | (required) | Google AI Studio key |
| `COINMARKETCAP_API_KEY`, `ETHERSCAN_API_KEY`, `DUNE_API_KEY` | | enable those sources |
| `ALLOWED_ORIGINS` | `*` | comma-separated CORS origins |
| `ADMIN_TOKEN` | (unset) | enables `/api/sessions` |
| `TOOL_TIMEOUT_SECONDS` | 40 | per-tool budget |
| `PLANNER_TIMEOUT_SECONDS` | 15 | planner/reflection budget before falling back |
| `AIRAA_TOOL_RETRIES` | 1 | retries on transient tool errors |
| `AIRAA_MAX_FOLLOWUP_ROUNDS` | 1 | extra gather rounds after reflection |
| `AIRAA_RATE_LIMIT_PER_MINUTE` | 20 | per client; `0` disables |
| `AIRAA_MAX_SESSIONS`, `AIRAA_SESSION_TTL_HOURS` | 200, 24 | in-process session cache limits (the database keeps history) |
| `DATABASE_URL`, `AIRAA_JWT_SECRET`, ... | (unset) | persistence and wallet features; see `.env.example` for the full list |

## Add a tool

1. Create `airaa/tools/<name>.py` with an `@tool async def <name>_tool(query: str, ...)` that returns
   `{"success": bool, "data": ..., "source": "<name>", "metadata": {...}}` and never raises.
2. Register it in `airaa/tools/__init__.py` (`TOOLS` and `TOOL_CATALOG`) and add `"<name>_tool"` to the `ToolName` literal in `airaa/schemas.py`.
3. Map its arguments in `build_tool_args` (`agent/executor.py`), add a merge branch in `agent/merge.py` and a renderer in `agent/context.py`.
4. Add a mocked-HTTP test in `tests/test_tools.py`.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The suite is offline: LLMs, embeddings and tools are faked, HTTP goes through `httpx.MockTransport`. `tests/integration/`
runs the migrations, every repository and the whole HTTP surface against a real Postgres with pgvector: it starts an
embedded one through `pgserver` (in `requirements-dev.txt`), or uses `AIRAA_TEST_DATABASE_URL` if you point it at a
disposable database, and is skipped if neither is available. `tests/manual/` holds older scripts that call live APIs and
need updating before use.

## Limits worth knowing

- Without `DATABASE_URL`, sessions live in process memory: lost on restart and not shared across gunicorn workers.
- The rate limiter is per process, so with N workers the effective limit is N times higher.
- The Dune tool supports DEX pair/volume questions only.
- Guest session ids are chosen by the client and act as a bearer secret; sign in with a wallet to make conversations private.
- Guest conversations untouched for 30 days are deleted; wallet-owned ones never expire on their own.
