"""HTTP access for tools.

One ``httpx.AsyncClient`` is created per research run (see :func:`client_scope`) and shared
by that run's tools through a ``ContextVar``. A process-wide client would be bound to a single
event loop, and the Flask layer runs each request on its own loop, so one request could close
a client another request was still using.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
from contextvars import ContextVar
from typing import AsyncIterator, Optional

import httpx

logger = logging.getLogger(__name__)

_client_var: ContextVar[Optional[httpx.AsyncClient]] = ContextVar("airaa_http_client", default=None)

_LIMITS = httpx.Limits(max_connections=50, max_keepalive_connections=10)
_TIMEOUT = httpx.Timeout(30.0, connect=10.0)
RETRYABLE_STATUS = {429, 500, 502, 503, 504}


@contextlib.asynccontextmanager
async def client_scope() -> AsyncIterator[httpx.AsyncClient]:
    """Create a client for the duration of a research run and make it the current one."""
    client = httpx.AsyncClient(timeout=_TIMEOUT, limits=_LIMITS, follow_redirects=True)
    token = _client_var.set(client)
    try:
        yield client
    finally:
        _client_var.reset(token)
        await client.aclose()


async def request(method: str, url: str, **kwargs) -> httpx.Response:
    """Issue a request on the current run's client (or a one-off client outside a run)."""
    client = _client_var.get()
    if client is not None:
        return await client.request(method.upper(), url, **kwargs)
    async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as one_off:
        return await one_off.request(method.upper(), url, **kwargs)


async def get(url: str, **kwargs) -> httpx.Response:
    return await request("GET", url, **kwargs)


async def post(url: str, **kwargs) -> httpx.Response:
    return await request("POST", url, **kwargs)


async def get_json(url: str, **kwargs):
    """GET and decode JSON; returns ``None`` on any HTTP or decoding failure."""
    try:
        response = await get(url, **kwargs)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError, asyncio.TimeoutError) as exc:
        logger.warning("GET %s failed: %s", url, exc)
        return None
