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

import logging
import threading
from typing import Any, AsyncIterator, Dict, List, Optional, Sequence, Tuple

from langchain_google_genai import ChatGoogleGenerativeAI

from ..config import Settings, get_settings

logger = logging.getLogger(__name__)

_cache: Dict[Tuple[str, int], ChatGoogleGenerativeAI] = {}
_lock = threading.Lock()


def build_llm(model: str, settings: Settings | None = None, max_tokens: int | None = None) -> ChatGoogleGenerativeAI:
    """Return a cached chat model. Raises ``RuntimeError`` if no API key is configured."""
    settings = settings or get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    key = (model, max_tokens or settings.max_output_tokens)
    with _lock:
        if key not in _cache:
            _cache[key] = ChatGoogleGenerativeAI(
                model=model,
                google_api_key=settings.gemini_api_key,
                max_tokens=key[1],
                max_retries=1,  # fail over to the next model instead of retrying an overloaded one
                timeout=90,
            )
        return _cache[key]


_genai_client = None


def genai_client():
    """Shared ``google.genai`` client for features LangChain does not wrap (URL context)."""
    global _genai_client
    from google import genai

    with _lock:
        if _genai_client is None:
            settings = get_settings()
            if not settings.gemini_api_key:
                raise RuntimeError("GEMINI_API_KEY is not configured")
            _genai_client = genai.Client(api_key=settings.gemini_api_key)
        return _genai_client


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


class FallbackModel:
    """Duck-typed chat model: ``with_structured_output(schema).ainvoke(...)`` and ``astream(...)``.

    Create one per request (cheap; the underlying clients are cached) so ``used`` is not shared
    between concurrent requests.
    """

    def __init__(self, models: Sequence[ChatGoogleGenerativeAI]) -> None:
        if not models:
            raise RuntimeError("No models configured")
        self.models = list(models)
        self.used: Optional[str] = None

    @property
    def names(self) -> List[str]:
        return [m.model for m in self.models]

    def with_structured_output(self, schema: Any) -> _FallbackStructured:
        return _FallbackStructured(self, schema)

    async def astream(self, messages: Any) -> AsyncIterator[Any]:
        errors: List[str] = []
        for model in self.models:
            started = False
            try:
                async for chunk in model.astream(messages):
                    started = True
                    yield chunk
                self.used = model.model
                return
            except Exception as exc:  # noqa: BLE001
                if started:
                    raise  # cannot switch models halfway through an answer
                errors.append(f"{model.model}: {_short(exc)}")
                logger.warning("Streaming failed on %s (%s); trying next model", model.model, _short(exc))
        raise RuntimeError("All models failed: " + "; ".join(errors))


def _chain(primary: str, fallbacks: Sequence[str], settings: Settings, max_tokens: int | None) -> FallbackModel:
    names = list(dict.fromkeys([primary, *fallbacks]))
    return FallbackModel([build_llm(n, settings, max_tokens) for n in names])


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
