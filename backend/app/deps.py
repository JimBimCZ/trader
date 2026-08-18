"""FastAPI dependencies.

Services are constructed once during startup and stored on `app.state`; these
accessors hand them to route handlers. Keeping construction in the lifespan
and lookup here means no module-level globals and no import-time side effects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request

if TYPE_CHECKING:
    from .history import HistoryStore
    from .llm.service import ChatService
    from .portfolio.service import TradeService
    from .watchlist.service import WatchlistService


def get_trade_service(request: Request) -> TradeService:
    return request.app.state.trade_service


def get_watchlist_service(request: Request) -> WatchlistService:
    return request.app.state.watchlist_service


def get_chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


def get_history_store(request: Request) -> HistoryStore:
    return request.app.state.history_store


TradeServiceDep = Annotated["TradeService", Depends(get_trade_service)]
WatchlistServiceDep = Annotated["WatchlistService", Depends(get_watchlist_service)]
ChatServiceDep = Annotated["ChatService", Depends(get_chat_service)]
HistoryStoreDep = Annotated["HistoryStore", Depends(get_history_store)]
