"""FastAPI dependencies.

Services are constructed once during startup and stored on `app.state`; these
accessors hand them to route handlers. Keeping construction in the lifespan
and lookup here means no module-level globals and no import-time side effects.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request, Response

from .identity import COOKIE_MAX_AGE, COOKIE_NAME, SessionCookie, User, UserStore

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


async def get_current_user(request: Request, response: Response) -> User:
    """Resolve the caller, minting and seeding a guest when there is none.

    A cookie that does not verify -- tampered, signed with a rotated secret,
    or pointing at a row a database reset removed -- is treated exactly like
    no cookie at all. Handing back a 401 would be wrong: there is nothing to
    log in to yet, and the honest answer to an unreadable session is a fresh
    one.
    """
    store: UserStore = request.app.state.user_store
    cookie: SessionCookie = request.app.state.session_cookie

    user_id = cookie.verify(request.cookies.get(COOKIE_NAME))
    user = await store.get(user_id) if user_id else None

    if user is None:
        user = await store.mint_guest()
        _set_session_cookie(request, response, cookie, user.id)
    else:
        await store.touch(user)

    return user


def _set_session_cookie(
    request: Request, response: Response, cookie: SessionCookie, user_id: str
) -> None:
    """Attach the session cookie.

    `Secure` is set everywhere except localhost: a Secure cookie is dropped
    by the browser over plain http, which would make local development mint a
    new guest on every single request.
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie.sign(user_id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=request.url.hostname not in ("localhost", "127.0.0.1"),
        path="/",
    )


CurrentUserDep = Annotated["User", Depends(get_current_user)]
