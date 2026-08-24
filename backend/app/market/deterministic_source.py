"""A price cache and data source backed by the deterministic model.

The rest of the application reads prices through `PriceCache` and drives the
tracked-ticker set through `MarketDataSource`. Reimplementing those two seams on
top of `deterministic.price_at` is the whole of the integration: SSE streaming,
trade pricing, portfolio valuation, the reconciler and `/api/health` all keep
working without knowing that nothing is filling the cache any more.
"""

from __future__ import annotations

import logging

from ..clock import now_ts
from .cache import PriceCache
from .deterministic import SESSION_SECONDS, price_at, seed_price
from .interface import MarketDataSource
from .models import PriceUpdate
from .tickers import canonicalize_ticker

logger = logging.getLogger(__name__)


class DeterministicPriceCache(PriceCache):
    """A `PriceCache` that computes on read instead of being written to.

    Prices are quantised onto a tick grid rather than evaluated at the exact
    wall clock. Two things depend on that: the SSE generator only emits when
    `version` changes, and the history store drops repeated timestamps — both of
    which need a price that holds still between ticks.
    """

    def __init__(
        self,
        tickers: list[str] | None = None,
        tick_seconds: float = 0.5,
        seed: int = 0,
        vol_multiplier: float = 1.0,
    ) -> None:
        super().__init__()
        self._tick_seconds = tick_seconds
        self._seed = seed
        self._vol_multiplier = vol_multiplier
        self._tracked: set[str] = {canonicalize_ticker(t) for t in (tickers or [])}

    # --- The tick grid ---

    def current_tick(self) -> int:
        return int(now_ts() // self._tick_seconds)

    def tick_time(self, tick: int) -> float:
        return tick * self._tick_seconds

    def build_update(self, ticker: str, tick: int) -> PriceUpdate:
        """The price for a ticker at a given tick, with its predecessor.

        At the first tick of a session the predecessor lies in the previous one,
        where the walk ended somewhere else entirely. Reporting that as a
        tick-over-tick change would fire a full-width flash on every row once a
        day, so the session opens flat instead.
        """
        now = self.tick_time(tick)
        previous_time = self.tick_time(tick - 1)
        price = price_at(ticker, now, self._seed, self._vol_multiplier)

        same_session = int(now // SESSION_SECONDS) == int(previous_time // SESSION_SECONDS)
        previous = (
            price_at(ticker, previous_time, self._seed, self._vol_multiplier)
            if same_session
            else price
        )

        return PriceUpdate(
            ticker=ticker,
            price=price,
            previous_price=previous,
            timestamp=now,
            session_open=seed_price(ticker),
        )

    # --- PriceCache surface ---

    def update(
        self,
        ticker: str,
        price: float,
        timestamp: float | None = None,
        session_open: float | None = None,
    ) -> PriceUpdate:
        """Start tracking a ticker. The supplied price is ignored.

        Kept write-shaped so that anything reaching for the documented cache API
        registers the ticker rather than silently doing nothing.
        """
        canonical = canonicalize_ticker(ticker)
        self._tracked.add(canonical)
        return self.build_update(canonical, self.current_tick())

    def get(self, ticker: str) -> PriceUpdate | None:
        canonical = canonicalize_ticker(ticker)
        if canonical not in self._tracked:
            return None
        return self.build_update(canonical, self.current_tick())

    def get_all(self) -> dict[str, PriceUpdate]:
        tick = self.current_tick()
        return {ticker: self.build_update(ticker, tick) for ticker in sorted(self._tracked)}

    def get_price(self, ticker: str) -> float | None:
        update = self.get(ticker)
        return update.price if update else None

    def remove(self, ticker: str) -> None:
        self._tracked.discard(canonicalize_ticker(ticker))

    @property
    def version(self) -> int:
        """The tick index, so a consumer watching for change sees one per tick."""
        return self.current_tick()

    def __len__(self) -> int:
        return len(self._tracked)

    def __contains__(self, ticker: str) -> bool:
        return canonicalize_ticker(ticker) in self._tracked

    @property
    def tickers(self) -> list[str]:
        return sorted(self._tracked)


class DeterministicDataSource(MarketDataSource):
    """A `MarketDataSource` with no background task, because there is nothing to run."""

    def __init__(self, price_cache: DeterministicPriceCache) -> None:
        self._cache = price_cache

    async def start(self, tickers: list[str]) -> None:
        for ticker in tickers:
            self._cache.update(ticker, 0.0)
        logger.info("Deterministic market source ready with %d tickers", len(tickers))

    async def stop(self) -> None:
        """Nothing to tear down."""

    async def add_ticker(self, ticker: str) -> None:
        self._cache.update(ticker, 0.0)
        logger.info("Deterministic source: added ticker %s", canonicalize_ticker(ticker))

    async def remove_ticker(self, ticker: str) -> None:
        self._cache.remove(ticker)
        logger.info("Deterministic source: removed ticker %s", canonicalize_ticker(ticker))

    def get_tickers(self) -> list[str]:
        return self._cache.tickers
