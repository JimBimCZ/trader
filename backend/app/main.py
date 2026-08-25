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
from starlette.middleware.sessions import SessionMiddleware

from .auth import build_oauth
from .auth import router as auth_module
from .auth.claim import ClaimToken
from .config import Settings
from .db import init_db, open_database, run_migrations
from .errors import FrontendNotBuiltError, RouteNotFoundError, register_exception_handlers
from .history import HistoryCollector, HistoryStore
from .history import router as history_module
from .identity import SessionCookie, UserStore
from .llm import create_chat_client
from .llm import router as chat_module
from .market import PriceCache, create_market_data_source, create_price_cache, create_stream_router
from .market.deterministic_source import DeterministicPriceCache
from .portfolio import router as portfolio_module
from .portfolio.snapshot_writer import SnapshotWriter
from .reconcile import TickerReconciler
from .system import router as system_module
from .system.cleanup import GuestCleaner
from .watchlist import router as watchlist_module

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
        # Un-locked, two instances race two separate check-then-act steps
        # (CREATE TABLE IF NOT EXISTS and the ADD CONSTRAINT existence
        # check) and one loses with a DuplicateObjectError instead of just
        # waiting its turn. ADD CONSTRAINT is transactional in Postgres, so
        # a transaction is sufficient -- no separate advisory-lock call
        # needed beyond what transaction() already takes.
        # Nothing is seeded here any more: a fresh database has no users at
        # all until the first request mints one, because there is no "the"
        # user to seed.
        async with db.transaction():
            await init_db(db)
            await run_migrations(db)

        app.state.user_store = UserStore(db, settings)
        app.state.session_cookie = SessionCookie(settings.session_secret)

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

        # Process-wide, not per request: they exist to order concurrent
        # writes within one instance, which is precisely what a lock created
        # fresh for each request could not do.
        trade_lock = asyncio.Lock()
        watchlist_lock = asyncio.Lock()

        # Serverless gets no writer at all. Its loop would never be scheduled
        # between requests, and `start()` is not free any more: it awaits one
        # snapshot write per user active in the last hour, so every cold start
        # would pay N Neon round trips before serving anything, growing with
        # adoption. `GET /api/portfolio` calls `write_snapshot_if_stale()`
        # there instead -- scoped to a user who is actually looking at the app.
        if not settings.serverless:
            snapshot_writer = SnapshotWriter(
                db,
                settings,
                app.state.user_store,
                price_cache,
                settings.snapshot_interval_seconds,
                settings.snapshot_retention_days,
            )
            await snapshot_writer.start()
            stack.push_async_callback(snapshot_writer.stop)

        # Nothing runs between requests on a serverless instance, so idle
        # guests there are expired by Vercel Cron hitting the admin route
        # instead of this background task.
        if not settings.serverless:
            cleaner = GuestCleaner(app.state.user_store, settings)
            await cleaner.start()
            stack.push_async_callback(cleaner.stop)

        app.state.db = db
        app.state.source = source
        app.state.history_store = history_store
        app.state.reconciler = reconciler
        app.state.chat_client = create_chat_client(settings)
        app.state.trade_lock = trade_lock
        app.state.watchlist_lock = watchlist_lock

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

    # Authlib parks the PKCE verifier and the state here. It must be a cookie
    # rather than process memory: serverless instances share nothing, so an
    # in-memory store fails intermittently and unreproducibly -- the worst
    # possible failure mode for a login button.
    app.add_middleware(
        SessionMiddleware,
        secret_key=resolved.session_secret,
        session_cookie="trader_oauth",
        max_age=600,
        same_site="lax",
        https_only=False,
    )

    app.state.oauth = build_oauth(resolved)
    app.state.claim_token = ClaimToken(resolved.session_secret)

    register_exception_handlers(app)

    # API routes first: the SPA fallback below matches everything, so any
    # route registered after it would be unreachable.
    app.include_router(auth_module.router)
    app.include_router(portfolio_module.router)
    app.include_router(watchlist_module.router)
    app.include_router(history_module.router)
    app.include_router(chat_module.router)
    app.include_router(system_module.router)

    app.include_router(
        create_stream_router(app.state.price_cache, max_seconds=resolved.stream_max_seconds)
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
        # `trailingSlash: true` exports every route as its own directory, so a
        # second page is `<route>/index.html` on disk rather than a bare file.
        # Trying only the first would answer /privacy/ with the app shell --
        # invisible on Vercel, whose CDN resolves the directory itself, and so
        # wrong only on the container target. Both lookups keep the same guard:
        # serve from inside the static root, never a traversal target.
        for target in (candidate, candidate / "index.html"):
            if target.is_file() and static_root in target.parents:
                return FileResponse(target)

        index = static_root / "index.html"
        if index.is_file():
            return FileResponse(index, headers={"Cache-Control": "no-store"})

        raise FrontendNotBuiltError(
            "Frontend has not been built. Run the frontend build, or use the API directly."
        )


# Loaded before settings are read, so a local .env reaches Settings.from_env().
load_local_env()
app = create_app()
