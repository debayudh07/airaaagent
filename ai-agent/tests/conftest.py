"""Shared fixtures: offline settings, fake LLMs, fake tools and a mock HTTP transport."""
from __future__ import annotations

import asyncio
from typing import Any, Callable, Dict, List, Optional

import httpx
import pytest

from airaa import http
from airaa.config import Settings
from airaa.memory import SessionManager
from airaa.schemas import FollowUp, Plan


@pytest.fixture(autouse=True)
def _offline_env(monkeypatch):
    """Never let a developer's real keys leak into tests."""
    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "COINMARKETCAP_API_KEY", "ETHERSCAN_API_KEY", "DUNE_API_KEY", "ADMIN_TOKEN",
                 "DATABASE_URL", "AIRAA_JWT_SECRET", "SUPABASE_JWT_SECRET", "SUPABASE_URL", "SUPABASE_SERVICE_ROLE_KEY",
                 "AIRAA_CRON_SECRET", "ALLOWED_ORIGINS", "AIRAA_SIWE_DOMAINS"):
        monkeypatch.delenv(name, raising=False)
    from airaa import services as _services
    from airaa.db import pool as _pool

    _services.reset_services()
    monkeypatch.setattr(_pool, "_pool", None)
    monkeypatch.setattr(_pool, "_failed", False)


@pytest.fixture
def settings() -> Settings:
    return Settings(
        gemini_api_key="test", coinmarketcap_api_key="cmc", etherscan_api_key="eth", dune_api_key="dune",
        tool_timeout_seconds=1.0, planner_timeout_seconds=1.0, tool_retries=1, rate_limit_per_minute=0,
    )


@pytest.fixture
def sessions() -> SessionManager:
    return SessionManager(max_sessions=10, ttl_hours=1)


# ----------------------------------------------------------------------- fake LLMs
class FakeStructured:
    def __init__(self, value: Any = None, error: Optional[Exception] = None, delay: float = 0.0):
        self.value, self.error, self.delay = value, error, delay
        self.calls: List[Any] = []

    async def ainvoke(self, messages):
        self.calls.append(messages)
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.value


class FakePlannerLLM:
    """Stands in for the planner model: ``with_structured_output(Plan|FollowUp)`` returns canned objects."""

    def __init__(self, plan: Optional[Plan] = None, followup: Optional[FollowUp] = None,
                 plan_error: Optional[Exception] = None, delay: float = 0.0):
        self.plan_runner = FakeStructured(plan, plan_error, delay)
        self.follow_runner = FakeStructured(followup or FollowUp(needs_more=False))

    def with_structured_output(self, schema):
        return self.plan_runner if schema is Plan else self.follow_runner


class Chunk:
    def __init__(self, text: str):
        self.text = text


class FakeSynthesisLLM:
    def __init__(self, pieces: Optional[List[str]] = None, error: Optional[Exception] = None):
        self.pieces = pieces if pieces is not None else ["Here is ", "the answer."]
        self.error = error
        self.calls: List[Any] = []

    async def astream(self, messages):
        self.calls.append(messages)
        if self.error:
            raise self.error
        for piece in self.pieces:
            yield Chunk(piece)


# ----------------------------------------------------------------------- fake tools
class FakeTool:
    """Drop-in for a LangChain tool: records calls and replays scripted results."""

    def __init__(self, *results: Dict[str, Any], delay: float = 0.0):
        self.results = list(results)
        self.delay = delay
        self.calls: List[Dict[str, Any]] = []

    async def ainvoke(self, args):
        self.calls.append(args)
        if self.delay:
            await asyncio.sleep(self.delay)
        return self.results[min(len(self.calls) - 1, len(self.results) - 1)]


@pytest.fixture
def patch_tools(monkeypatch):
    """Replace entries in the tool registry for the duration of a test."""
    from airaa.tools import TOOLS

    def _apply(**tools):
        for name, tool in tools.items():
            monkeypatch.setitem(TOOLS, name, tool)

    return _apply


# ----------------------------------------------------------------------- HTTP mocking
@pytest.fixture
def mock_http():
    """``mock_http(handler)`` routes every ``airaa.http`` request through ``handler(httpx.Request)``."""
    tokens = []

    def _install(handler: Callable[[httpx.Request], httpx.Response]) -> List[httpx.Request]:
        seen: List[httpx.Request] = []

        def wrapped(request: httpx.Request) -> httpx.Response:
            seen.append(request)
            return handler(request)

        client = httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
        tokens.append(http._client_var.set(client))
        return seen

    yield _install
    for token in reversed(tokens):
        http._client_var.reset(token)


def run(coro):
    return asyncio.run(coro)
