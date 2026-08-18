"""Tests for the SSE streaming router and event generator."""

from __future__ import annotations

import json

import pytest

from app.market.cache import PriceCache
from app.market.stream import _KEEPALIVE_FRAME, _generate_events, create_stream_router


class FakeRequest:
    """Minimal stand-in for a Starlette Request.

    Reports connected for `connected_for` checks, then disconnected, so the
    generator terminates deterministically instead of looping forever.
    """

    def __init__(self, connected_for: int = 2) -> None:
        self._remaining = connected_for
        self.client = None

    async def is_disconnected(self) -> bool:
        if self._remaining <= 0:
            return True
        self._remaining -= 1
        return False


class TestCreateStreamRouter:
    def test_returns_a_router_with_the_prices_route(self):
        """The factory mounts GET /api/stream/prices."""
        router = create_stream_router(PriceCache())
        paths = [route.path for route in router.routes]
        assert "/api/stream/prices" in paths

    def test_each_call_returns_an_independent_router(self):
        """Two calls must not share one module-level router.

        The factory used to decorate a router defined at module scope, so a
        second call registered a duplicate route on the same object and the
        first closure's cache won for both apps.
        """
        first = create_stream_router(PriceCache())
        second = create_stream_router(PriceCache())
        assert first is not second
        assert len(first.routes) == 1
        assert len(second.routes) == 1


@pytest.mark.asyncio
class TestGenerateEvents:
    async def test_first_frame_is_the_retry_directive(self):
        """The stream opens with a retry directive so EventSource reconnects."""
        cache = PriceCache()
        gen = _generate_events(cache, FakeRequest(connected_for=0), interval=0.01)
        assert await anext(gen) == "retry: 1000\n\n"

    async def test_emits_all_tickers_in_one_frame(self):
        """One event carries a map of every cached ticker, not one event each."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        cache.update("MSFT", 420.0)

        frames = [frame async for frame in _generate_events(cache, FakeRequest(1), interval=0.01)]
        data_frames = [f for f in frames if f.startswith("data: ")]
        assert len(data_frames) == 1

        payload = json.loads(data_frames[0].removeprefix("data: ").strip())
        assert sorted(payload) == ["AAPL", "MSFT"]
        assert payload["AAPL"]["price"] == 190.0

    async def test_payload_carries_the_session_baseline(self):
        """Each ticker's payload includes session_open and the daily fields."""
        cache = PriceCache()
        cache.update("AAPL", 190.0, session_open=190.0)
        cache.update("AAPL", 199.5)

        frames = [frame async for frame in _generate_events(cache, FakeRequest(1), interval=0.01)]
        payload = json.loads(
            next(f for f in frames if f.startswith("data: ")).removeprefix("data: ").strip()
        )
        assert payload["AAPL"]["session_open"] == 190.0
        assert payload["AAPL"]["daily_change_percent"] == 5.0

    async def test_does_not_re_emit_an_unchanged_cache(self):
        """A cache whose version has not moved produces no further data frames."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)

        frames = [frame async for frame in _generate_events(cache, FakeRequest(3), interval=0.01)]
        assert len([f for f in frames if f.startswith("data: ")]) == 1

    async def test_empty_cache_emits_no_data_frames(self):
        """Before any price exists, only the retry directive is sent."""
        cache = PriceCache()
        frames = [frame async for frame in _generate_events(cache, FakeRequest(2), interval=0.01)]
        assert not [f for f in frames if f.startswith("data: ")]

    async def test_sends_a_keepalive_when_idle(self, monkeypatch):
        """A quiet cache still produces traffic so idle proxies do not drop us."""
        monkeypatch.setattr("app.market.stream._KEEPALIVE_INTERVAL", 0.0)
        cache = PriceCache()
        cache.update("AAPL", 190.0)

        frames = [frame async for frame in _generate_events(cache, FakeRequest(3), interval=0.01)]
        assert _KEEPALIVE_FRAME in frames

    async def test_stops_when_the_client_disconnects(self):
        """The generator terminates rather than looping after a disconnect."""
        cache = PriceCache()
        cache.update("AAPL", 190.0)
        frames = [frame async for frame in _generate_events(cache, FakeRequest(1), interval=0.01)]
        assert frames  # terminated without hanging
