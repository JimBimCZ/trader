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
from contextlib import AsyncExitStack, asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse

from .config import Settings
from .db import init_db, open_database, run_migrations, seed_if_empty
from .errors import FrontendNotBuiltError, RouteNotFoundError, register_exception_handlers
from .history import HistoryCollector, HistoryStore
from .history import router as history_module
from .identity import SessionCookie, UserStore
from .llm import ActionExecutor, ChatRepository, ChatService, create_chat_client
from .llm import router as chat_module
from .market import PriceCache, create_market_data_source, create_price_cache, create_stream_router
from .market.deterministic_source import DeterministicPriceCache
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


def _build_history_store(settings: Settings, price_cache: PriceCache) -> HistoryStore:
    """The ring buffer, or the computed history that makes it unnecessary."""
    if isinstance(price_cache, DeterministicPriceCache):
        from .history.deterministic import DeterministicHistoryStore

        return DeterministicHistoryStore(price_cache, maxlen=settings.history_maxlen)
    return HistoryStore(maxlen=settings.history_maxlen)


async def _log_shutdown_complete() -> None:
    logger.info("Shutdown complete")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Start every subsystem in dependency order, then tear it down.

    The database is initialized here rather than on first request: the market
    data source needs the watchlist to know which tickers to track, so it
    cannot wait for a request to arrive.
    """
    settings: Settings = app.state.settings

    # Every subsystem registers its own teardown the moment it starts, so a
    # failure anywhere in startup unwinds exactly what is already running --
    # in reverse order -- instead of leaking it. A plain try/finally around
    # the yield cannot do this: it only begins once startup has fully
    # succeeded, so a raise partway through used to leak the pool AND leave
    # an already-started market source running.
    async with AsyncExitStack() as stack:
        # Registered first so it runs last, after every stop() above it has
        # finished -- the message would otherwise be printed while teardown
        # was still in progress.
        stack.push_async_callback(_log_shutdown_complete)

        db = await open_database(settings)
        stack.push_async_callback(db.close)

        # Wrapped in one transaction, holding the cross-instance advisory
        # lock for its whole duration: Vercel starts more than one instance
        # concurrently, and each runs this same sequence on cold start.
        # Un-locked, two instances race three separate check-then-act steps
        # (CREATE TABLE IF NOT EXISTS, the seed SELECT-then-INSERT, and the
        # ADD CONSTRAINT existence check) and one loses with a
        # UniqueViolationError / DuplicateObjectError instead of just
        # waiting its turn. ADD CONSTRAINT is transactional in Postgres, so
        # a transaction is sufficient -- no separate advisory-lock call
        # needed beyond what transaction() already takes.
        # Seeding must still precede migrating: migration 001 adds foreign
        # keys to users_profile, and every per-user row must already point
        # at a profile that exists.
        async with db.transaction():
            await init_db(db)
            await seed_if_empty(db, settings)
            await run_migrations(db)

        app.state.user_store = UserStore(db, settings)
        app.state.session_cookie = SessionCookie(settings.session_secret)

        users = UserRepository(db)
        positions = PositionRepository(db)
        trades = TradeRepository(db)
        snapshots = SnapshotRepository(db)
        watchlist_repo = WatchlistRepository(db)
        chat_repo = ChatRepository(db)

        price_cache: PriceCache = app.state.price_cache
        source = create_market_data_source(price_cache, settings)
        reconciler = TickerReconciler(source, db, settings.market_capacity)

        tracked = await reconciler.compute_tracked_tickers()
        await source.start(tracked)
        stack.push_async_callback(source.stop)

        history_store = _build_history_store(settings, price_cache)
        for ticker in tracked:
            history_store.track(ticker)
        # Computed history has nothing to collect, and a serverless instance is
        # frozen between requests so the task would not run anyway.
        collector: HistoryCollector | None = None
        if not settings.serverless and not isinstance(price_cache, DeterministicPriceCache):
            collector = HistoryCollector(price_cache, history_store, settings.history_poll_seconds)
            await collector.start()
            stack.push_async_callback(collector.stop)

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

        # Nothing runs between requests on a serverless platform, so the periodic
        # snapshot moves into the SSE stream — which is open exactly when someone
        # is watching the chart it feeds.
        snapshot_writer: SnapshotWriter | None = None
        if settings.serverless:
            await trade_service.write_snapshot()
        else:
            snapshot_writer = SnapshotWriter(
                trade_service, settings.snapshot_interval_seconds, settings.snapshot_retention_days
            )
            await snapshot_writer.start()
            stack.push_async_callback(snapshot_writer.stop)

        app.state.db = db
        app.state.source = source
        app.state.history_store = history_store
        app.state.trade_service = trade_service
        app.state.watchlist_service = watchlist_service
        app.state.chat_service = chat_service
        app.state.reset_service = reset_service

        logger.info("Startup complete: %d tickers tracked", len(tracked))
        yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application. Pure construction; startup happens in lifespan."""
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-8s %(name)s: %(message)s"
    )

    app = FastAPI(title="Trader", version="0.1.0", lifespan=lifespan)
    resolved = settings or Settings.from_env()
    app.state.settings = resolved
    # The cache has no I/O, so it can be created here and shared with the SSE
    # router; startup only fills it — or, for the computed cache, only names
    # the tickers it should answer for.
    app.state.price_cache = create_price_cache(resolved)

    register_exception_handlers(app)

    # API routes first: the SPA fallback below matches everything, so any
    # route registered after it would be unreachable.
    app.include_router(portfolio_module.router)
    app.include_router(watchlist_module.router)
    app.include_router(history_module.router)
    app.include_router(chat_module.router)
    app.include_router(system_module.router)

    async def write_snapshot_from_stream() -> None:
        """Late-bound: the trade service does not exist until startup runs."""
        service = getattr(app.state, "trade_service", None)
        if service is not None:
            await service.write_snapshot()

    app.include_router(
        create_stream_router(
            app.state.price_cache,
            max_seconds=resolved.stream_max_seconds,
            on_heartbeat=write_snapshot_from_stream if resolved.serverless else None,
            heartbeat_seconds=resolved.snapshot_interval_seconds,
        )
    )

    _register_static_routes(app)
    return app


def _register_static_routes(app: FastAPI) -> None:
    """Serve the exported frontend, if it has been built into the image."""

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa(full_path: str) -> FileResponse:
        # An unmatched /api path is a wrong URL, not a request for the app
        # shell. Falling through would answer it with index.html, or — where
        # the frontend is served by a CDN rather than from here, as on
        # Vercel — with "frontend has not been built".
        if full_path == "api" or full_path.startswith("api/"):
            raise RouteNotFoundError(f"No API route matches /{full_path}.")

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
