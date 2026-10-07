"""Gemini model factories with automatic fallback.

Two roles with different cost/quality needs:

* ``planner``   - short structured decisions (which tools, follow-up?). Flash-Lite is plenty.
* ``synthesis`` - the user-facing analysis. Uses the stronger Flash model.

Each role is a *chain* of models. Gemini returns 503 ("high demand") and 429 (per-model quota)
regularly, especially on the free tier, and quotas are tracked per model, so trying the next model
usually succeeds where retrying the same one would not.

Temperature is left at the model default: Google recommends the default for the Gemini 3 family.
"""
from __future__ import annotations

import asyncio
import logging
import threading
import weakref
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence

from langchain_google_genai import ChatGoogleGenerativeAI

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

# Clients hold async HTTP connections bound to the event loop that first used them, and the Flask
# layer runs every request on a fresh loop. A process-wide cache therefore breaks from the second
# request on ("Event loop is closed" -> RuntimeError). Cache per running loop instead; entries go
# away with their loop.
_per_loop: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, Dict[Any, Any]]" = weakref.WeakKeyDictionary()
_lock = threading.Lock()


def _loop_cache() -> Dict[Any, Any]:
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return {}  # no loop (e.g. sync warm-up): build, do not cache
    with _lock:
        return _per_loop.setdefault(loop, {})


def build_llm(model: str, settings: Settings | None = None, max_tokens: int | None = None) -> ChatGoogleGenerativeAI:
    """Return a cached chat model. Raises ``RuntimeError`` if no API key is configured."""
    settings = settings or get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    key = (model, max_tokens or settings.max_output_tokens)
    cache = _loop_cache()
    if key not in cache:
        cache[key] = ChatGoogleGenerativeAI(
            model=model,
            google_api_key=settings.gemini_api_key,
            max_tokens=key[1],
            max_retries=1,  # fail over to the next model instead of retrying an overloaded one
            timeout=90,
        )
    return cache[key]


def genai_client():
    """``google.genai`` client for features LangChain does not wrap (URL context); cached per event loop."""
    from google import genai

    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    cache = _loop_cache()
    if "genai" not in cache:
        cache["genai"] = genai.Client(api_key=settings.gemini_api_key)
    return cache["genai"]


def _short(exc: Exception) -> str:
    text = str(exc)
    for marker in ("RESOURCE_EXHAUSTED", "UNAVAILABLE", "NOT_FOUND", "INVALID_ARGUMENT", "PERMISSION_DENIED", "DEADLINE"):
        if marker in text:
            return marker
    return type(exc).__name__


class _FallbackStructured:
    def __init__(self, owner: "FallbackModel", schema: Any) -> None:
        self.owner, self.schema = owner, schema

    async def ainvoke(self, messages: Any) -> Any:
        errors: List[str] = []
        for model in self.owner.models:
            try:
                result = await model.with_structured_output(self.schema).ainvoke(messages)
                self.owner.used = model.model
                return result
            except Exception as exc:  # noqa: BLE001 - any failure means "try the next model"
                errors.append(f"{model.model}: {_short(exc)}")
                logger.warning("Structured call failed on %s (%s); trying next model", model.model, _short(exc))
        raise RuntimeError("All models failed: " + "; ".join(errors))


# Yielded by FallbackModel.astream when a model failed AFTER some text was already streamed and the next model is
# starting over: the consumer must discard the draft it has accumulated so far.
STREAM_RESET: Any = object()


class FallbackModel:
    """Duck-typed chat model: ``with_structured_output(schema).ainvoke(...)`` and ``astream(...)``.

    Create one per request (cheap; the underlying clients are cached) so ``used`` is not shared
    between concurrent requests.
    """

    def __init__(self, models: Sequence[ChatGoogleGenerativeAI], first_token_timeout: float = 30.0) -> None:
        if not models:
            raise RuntimeError("No models configured")
        self.models = list(models)
        self.first_token_timeout = first_token_timeout
        self.used: Optional[str] = None

    @property
    def names(self) -> List[str]:
        return [m.model for m in self.models]

    def with_structured_output(self, schema: Any) -> _FallbackStructured:
        return _FallbackStructured(self, schema)

    async def astream(self, messages: Any) -> AsyncIterator[Any]:
        """Stream from the first model that produces text, moving on when a model

        * stalls: no text within ``first_token_timeout`` seconds (an overloaded model can hang for the full HTTP timeout),
        * returns an empty answer (no text and no exception), or
        * fails, even partway through (then :data:`STREAM_RESET` tells the consumer to discard the partial draft).
        """
        errors: List[str] = []
        for model in self.models:
            emitted = False
            iterator = model.astream(messages).__aiter__()
            try:
                while True:
                    try:
                        # Only the wait for the first text is bounded; after that the stream is flowing.
                        chunk = await (asyncio.wait_for(iterator.__anext__(), self.first_token_timeout)
                                       if not emitted else iterator.__anext__())
                    except StopAsyncIteration:
                        break
                    if text_of(chunk):
                        emitted = True
                    yield chunk
                if emitted:
                    self.used = model.model
                    return
                errors.append(f"{model.model}: empty answer")
                logger.warning("%s returned no text; trying next model", model.model)
            except Exception as exc:  # noqa: BLE001 - includes asyncio.TimeoutError
                reason = "timed out before its first token" if isinstance(exc, asyncio.TimeoutError) else _short(exc)
                errors.append(f"{model.model}: {reason}")
                logger.warning("Streaming failed on %s (%s); trying next model", model.model, reason)
                if emitted:
                    yield STREAM_RESET  # the next model starts the answer over
            finally:
                aclose = getattr(iterator, "aclose", None)
                if aclose is not None:
                    try:
                        await aclose()
                    except Exception:  # noqa: BLE001 - closing a broken stream may itself fail
                        pass
        raise RuntimeError("All models failed: " + "; ".join(errors))


def _chain(primary: str, fallbacks: Sequence[str], settings: Settings, max_tokens: int | None) -> FallbackModel:
    names = list(dict.fromkeys([primary, *fallbacks]))
    return FallbackModel([build_llm(n, settings, max_tokens) for n in names], settings.first_token_timeout_seconds)


def planner_llm(settings: Settings | None = None) -> FallbackModel:
    settings = settings or get_settings()
    return _chain(settings.planner_model, settings.planner_fallbacks, settings, 1024)


def synthesis_llm(settings: Settings | None = None) -> FallbackModel:
    settings = settings or get_settings()
    return _chain(settings.synthesis_model, settings.synthesis_fallbacks, settings, None)


def text_of(message: Any) -> str:
    """Plain text of a model response.

    Gemini 3 can return content as a list of blocks (thinking, text, ...); ``.text`` on a
    LangChain message joins only the text blocks. Falls back to ``str`` for plain strings.
    """
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    text = getattr(message, "text", None)
    if isinstance(text, str):  # langchain-core 1.x: a str subclass (also callable, hence checked first)
        return str(text)
    if callable(text):  # older langchain-core exposed .text() as a method
        text = text()
        if isinstance(text, str):
            return text
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part if isinstance(part, str) else part.get("text", "")
            for part in content if isinstance(part, (str, dict))
        )
    return str(content)
