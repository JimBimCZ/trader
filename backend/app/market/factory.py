"""Factories for the price cache and the market data source."""

from __future__ import annotations

import logging
import os

from ..config import Settings
from .cache import PriceCache
from .interface import MarketDataSource

logger = logging.getLogger(__name__)


def _deterministic_selected(settings: Settings | None) -> bool:
    if settings is not None:
        return settings.market_source == "deterministic" and not settings.massive_api_key.strip()
    return os.environ.get("MARKET_SOURCE", "").strip() == "deterministic"


def create_price_cache(settings: Settings | None = None) -> PriceCache:
    """The cache the rest of the app reads prices from.

    Two flavours, and the choice has to be made here rather than inside the
    data source: the SSE router is handed the cache at construction time, long
    before the source exists.
    """
    if _deterministic_selected(settings):
        from .deterministic_source import DeterministicPriceCache

        return DeterministicPriceCache(
            tick_seconds=settings.sim_tick_seconds if settings else 0.5,
            seed=(settings.sim_seed or 0) if settings else 0,
            vol_multiplier=settings.sim_vol_multiplier if settings else 1.0,
        )
    return PriceCache()


def create_market_data_source(
    price_cache: PriceCache, settings: Settings | None = None
) -> MarketDataSource:
    """Create the market data source that matches the cache and the environment.

    - `MASSIVE_API_KEY` set and non-empty → MassiveDataSource (real market data)
    - `MARKET_SOURCE=deterministic` → prices computed from the clock
    - otherwise → the stateful GBM simulator

    Every import is deferred, and stays inside its own branch: numpy belongs to
    the simulator and the massive client to the paid data path, and neither is
    installed in the serverless deployment. An import outside a branch — even
    one only reached to test a type — fails there at startup.

    The simulator's tuning knobs are applied here rather than by the caller,
    for the same reason: re-wrapping the returned source would mean naming its
    class, and naming it would mean importing it.

    Returns an unstarted source. Caller must await source.start(tickers).
    """
    api_key = (
        settings.massive_api_key if settings else os.environ.get("MASSIVE_API_KEY", "")
    ) or ""
    api_key = api_key.strip()

    if api_key:
        from .massive_client import MassiveDataSource

        logger.info("Market data source: Massive API (real data)")
        return MassiveDataSource(api_key=api_key, price_cache=price_cache)

    if _deterministic_selected(settings):
        from .deterministic_source import DeterministicDataSource, DeterministicPriceCache

        if not isinstance(price_cache, DeterministicPriceCache):
            raise TypeError(
                "The deterministic source computes prices on read and needs a "
                "DeterministicPriceCache; build it with create_price_cache()."
            )
        logger.info("Market data source: deterministic (computed from the clock)")
        return DeterministicDataSource(price_cache)

    from .simulator import SimulatorDataSource

    logger.info("Market data source: GBM Simulator")
    return SimulatorDataSource(
        price_cache=price_cache,
        update_interval=settings.sim_tick_seconds if settings else 0.5,
        seed=settings.sim_seed if settings else None,
        vol_multiplier=settings.sim_vol_multiplier if settings else 1.0,
    )
