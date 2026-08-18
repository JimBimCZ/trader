"""Helpers for building services against a temp database in tests."""

from __future__ import annotations

import asyncio

from app.config import Settings
from app.db import Database
from app.history import HistoryStore
from app.llm import ActionExecutor, ChatRepository, ChatService
from app.llm.mock_client import MockChatClient
from app.market import MarketDataSource, PriceCache
from app.portfolio.repository import (
    PositionRepository,
    SnapshotRepository,
    TradeRepository,
    UserRepository,
)
from app.portfolio.service import TradeService
from app.reconcile import TickerReconciler
from app.watchlist.repository import WatchlistRepository
from app.watchlist.service import WatchlistService


class StubDataSource(MarketDataSource):
    """In-memory MarketDataSource that records what it was asked to track.

    Lets tests assert the tracked-ticker invariants without running the
    simulator's background task.
    """

    def __init__(self, price_cache: PriceCache) -> None:
        self._cache = price_cache
        self._tickers: list[str] = []
        self.removed: list[str] = []

    async def start(self, tickers: list[str]) -> None:
        for ticker in tickers:
            await self.add_ticker(ticker)

    async def stop(self) -> None:
        return None

    async def add_ticker(self, ticker: str) -> None:
        """Track the ticker without inventing a price.

        Models the stricter case: the simulator seeds a price synchronously,
        but Massive only has one after its next poll, so nothing downstream
        may assume tracking implies a price.
        """
        if ticker not in self._tickers:
            self._tickers.append(ticker)

    async def remove_ticker(self, ticker: str) -> None:
        if ticker in self._tickers:
            self._tickers.remove(ticker)
        self.removed.append(ticker)
        self._cache.remove(ticker)

    def get_tickers(self) -> list[str]:
        return list(self._tickers)


class Services:
    """Everything a service-level test needs, wired together."""

    def __init__(self, db: Database, settings: Settings, price_cache: PriceCache) -> None:
        self.db = db
        self.settings = settings
        self.price_cache = price_cache

        self.users = UserRepository(db)
        self.positions = PositionRepository(db)
        self.trades = TradeRepository(db)
        self.snapshots = SnapshotRepository(db)
        self.watchlist_repo = WatchlistRepository(db)
        self.chat_repo = ChatRepository(db)

        self.source = StubDataSource(price_cache)
        self.reconciler = TickerReconciler(self.source, self.watchlist_repo, self.positions)

        self.trade_lock = asyncio.Lock()
        self.watchlist_lock = asyncio.Lock()

        self.trade_service = TradeService(
            db,
            self.users,
            self.positions,
            self.trades,
            self.snapshots,
            price_cache,
            self.reconciler,
            self.trade_lock,
        )
        self.watchlist_service = WatchlistService(
            db, self.watchlist_repo, self.reconciler, self.watchlist_lock, settings.watchlist_cap
        )
        self.history_store = HistoryStore(maxlen=settings.history_maxlen)
        self.chat_client = MockChatClient()
        self.executor = ActionExecutor(self.trade_service, self.watchlist_service)
        self.chat_service = ChatService(
            self.chat_repo,
            self.trade_service,
            self.watchlist_service,
            self.chat_client,
            self.executor,
            settings,
        )

    async def track(self, *tickers: str, price: float = 100.0) -> None:
        """Track tickers and give them a price, as a live source would."""
        for ticker in tickers:
            await self.source.add_ticker(ticker)
            self.price_cache.update(ticker, price, session_open=price)
