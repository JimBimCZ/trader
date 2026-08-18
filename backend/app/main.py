"""Application composition root.

Builds the FastAPI app, wires every service together during startup, and
serves the exported frontend. Nothing here is constructed at import time
beyond the app object itself, so tests can build an isolated instance.
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse

from .config import Settings
from .db import Database, init_db, open_connection, seed_if_empty
from .errors import FrontendNotBuiltError, register_exception_handlers
from .history import HistoryCollector, HistoryStore
from .history import router as history_module
from .llm import ActionExecutor, ChatRepository, ChatService, create_chat_client
from .llm import router as chat_module
from .market import PriceCache, create_market_data_source, create_stream_router
from .market.simulator import SimulatorDataSource
from .portfolio import router as portfolio_module
from .portfolio.repository import (
    PositionRepository,
    SnapshotRepository,
    TradeRepository,
    UserRepository,
)
from .portfolio.service import TradeService
from .portfolio.snapshot_writer import SnapshotWriter
from .reconcile import TickerReconciler
from .system import router as system_module
from .system.service import ResetService
from .watchlist import router as watchlist_module
from .watchlist.repository import WatchlistRepository
from .watchlist.service import WatchlistService

logger = logging.getLogger(__name__)

#: Where the built frontend is copied to in the Docker image.
STATIC_DIR = Path(os.environ.get("STATIC_DIR", "static"))


def load_local_env() -> None:
    """Load .env for local development.

    In Docker the variables arrive via --env-file and no .env exists inside
    the container, so this is a no-op there. Existing environment variables
    always win.
    """
    load_dotenv(override=False)


def _build_market_source(settings: Settings, price_cache: PriceCache):
    """Create the market data source, applying the simulator tuning knobs.

    create_market_data_source exposes no configuration, so the simulator's
    seed and tick rate are applied here rather than by editing the factory.
    """
    source = create_market_data_source(price_cache)
    if isinstance(source, SimulatorDataSource):
        return SimulatorDataSource(
            price_cache=price_cache,
            update_interval=settings.sim_tick_seconds,
            seed=settings.sim_seed,
        )
    return source


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start every subsystem in dependency order, then tear it down.

    The database is initialized here rather than on first request: the market
    data source needs the watchlist to know which tickers to track, so it
    cannot wait for a request to arrive.
    """
    settings: Settings = app.state.settings

    conn = await open_connection(settings.db_path)
    db = Database(conn)
    await init_db(db)
    await seed_if_empty(db, settings)

    users = UserRepository(db)
    positions = PositionRepository(db)
    trades = TradeRepository(db)
    snapshots = SnapshotRepository(db)
    watchlist_repo = WatchlistRepository(db)
    chat_repo = ChatRepository(db)

    price_cache: PriceCache = app.state.price_cache
    source = _build_market_source(settings, price_cache)
    reconciler = TickerReconciler(source, watchlist_repo, positions)

    tracked = await reconciler.compute_tracked_tickers()
    await source.start(tracked)

    history_store = HistoryStore(maxlen=settings.history_maxlen)
    for ticker in tracked:
        history_store.track(ticker)
    collector = HistoryCollector(price_cache, history_store, settings.history_poll_seconds)
    await collector.start()

    trade_lock = asyncio.Lock()
    watchlist_lock = asyncio.Lock()

    trade_service = TradeService(
        db, users, positions, trades, snapshots, price_cache, reconciler, trade_lock
    )
    watchlist_service = WatchlistService(
        db, watchlist_repo, reconciler, watchlist_lock, settings.watchlist_cap
    )
    chat_service = ChatService(
        chat_repo,
        trade_service,
        watchlist_service,
        create_chat_client(settings),
        ActionExecutor(trade_service, watchlist_service),
        settings,
    )
    reset_service = ResetService(
        db,
        settings,
        users,
        positions,
        trades,
        snapshots,
        watchlist_repo,
        chat_repo,
        reconciler,
        history_store,
        trade_lock,
        watchlist_lock,
    )

    snapshot_writer = SnapshotWriter(
        trade_service, settings.snapshot_interval_seconds, settings.snapshot_retention_days
    )
    await snapshot_writer.start()

    app.state.db = db
    app.state.source = source
    app.state.history_store = history_store
    app.state.trade_service = trade_service
    app.state.watchlist_service = watchlist_service
    app.state.chat_service = chat_service
    app.state.reset_service = reset_service

    logger.info("Startup complete: %d tickers tracked", len(tracked))
    try:
        yield
    finally:
        await snapshot_writer.stop()
        await collector.stop()
        await source.stop()
        await conn.close()
        logger.info("Shutdown complete")


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Pure construction; startup happens in lifespan."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    )

    app = FastAPI(title="Trader", version="0.1.0", lifespan=lifespan)
    app.state.settings = settings or Settings.from_env()
    # The cache is plain in-memory state with no I/O, so it can be created
    # here and shared with the SSE router; startup only fills it.
    app.state.price_cache = PriceCache()

    register_exception_handlers(app)

    # API routes first: the SPA fallback below matches everything, so any
    # route registered after it would be unreachable.
    app.include_router(portfolio_module.router)
    app.include_router(watchlist_module.router)
    app.include_router(history_module.router)
    app.include_router(chat_module.router)
    app.include_router(system_module.router)
    app.include_router(create_stream_router(app.state.price_cache))

    _register_static_routes(app)
    return app


def _register_static_routes(app: FastAPI) -> None:
    """Serve the exported frontend, if it has been built into the image."""

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        candidate = (STATIC_DIR / full_path).resolve()
        static_root = STATIC_DIR.resolve()
        # Only serve files inside the static root, never a traversal target.
        if candidate.is_file() and static_root in candidate.parents:
            return FileResponse(candidate)

        index = static_root / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-store"})

        raise FrontendNotBuiltError(
            "Frontend has not been built. Run the frontend build, or use the API directly."
        )


# Loaded before settings are read, so a local .env reaches Settings.from_env().
load_local_env()
app = create_app()
