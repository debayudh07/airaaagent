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
│   ├── memory.py          in-memory conversation sessions (TTL + size limits)
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
└── tests/                 pytest suite (offline); tests/manual holds old live-API scripts
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
| `AIRAA_MAX_SESSIONS`, `AIRAA_SESSION_TTL_HOURS` | 200, 24 | session store limits |

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

The suite is offline: LLMs and tools are faked, HTTP goes through `httpx.MockTransport`. `tests/manual/` holds older
scripts that call live APIs and need updating before use.

## Limits worth knowing

- Sessions live in process memory: lost on restart and not shared across gunicorn workers.
- The rate limiter is per process, so with N workers the effective limit is N times higher.
- The Dune tool supports DEX pair/volume questions only.
- Session ids are chosen by the client, so treat them as unguessable only if the client makes them so.
