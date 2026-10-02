import pytest

from airaa import feed
from airaa.api import create_app


@pytest.fixture(autouse=True)
def _fresh_cache():
    feed._cache.update(at=0.0, data=None)
    yield
    feed._cache.update(at=0.0, data=None)


def _stub_build(monkeypatch, result):
    calls = []

    async def fake_build():
        calls.append(1)
        return result

    monkeypatch.setattr(feed, "build_feed", fake_build)
    return calls


def test_feed_is_cached_within_ttl(monkeypatch):
    calls = _stub_build(monkeypatch, {"markets": [{"symbol": "BTC"}]})
    first = feed.get_feed(now=1000.0)
    second = feed.get_feed(now=1000.0 + feed.CACHE_TTL - 1)
    assert first is second
    assert len(calls) == 1
    feed.get_feed(now=1000.0 + feed.CACHE_TTL + 1)
    assert len(calls) == 2


def test_empty_feed_is_not_cached(monkeypatch):
    calls = _stub_build(monkeypatch, {})
    assert feed.get_feed(now=10.0)["sections"] == {}
    feed.get_feed(now=11.0)
    assert len(calls) == 2


def test_spark_downsamples_and_keeps_last_point():
    prices = [float(i) for i in range(500)]
    out = feed._spark(prices, limit=48)
    assert len(out) == 48
    assert out[-1] == 499.0


def test_feed_route(monkeypatch, settings):
    _stub_build(monkeypatch, {"news": [{"title": "Headline", "url": "https://example.com"}]})
    client = create_app(settings, agent_factory=lambda sid: None).test_client()
    res = client.get("/api/feed")
    body = res.get_json()
    assert res.status_code == 200
    assert body["success"] is True
    assert body["sections"]["news"][0]["title"] == "Headline"
    assert "max-age=60" in res.headers["Cache-Control"]
