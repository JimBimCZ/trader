"""FastAPI dependencies.

Services are built per request, scoped to the caller, rather than once during
startup: the user id is only known once a request arrives, and building here
is what makes it a required argument on every repository below. Everything
that is genuinely shared -- the pool, the price cache, the market source, the
reconciler, the two write locks -- still lives on `app.state` and is handed
to each fresh service.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, Request, Response

from .errors import PENDING_SESSION_COOKIE_ATTR
from .identity import COOKIE_MAX_AGE, COOKIE_NAME, SessionCookie, User, UserStore
from .llm import ActionExecutor, ChatRepository, ChatService
from .portfolio.service import build_trade_service
from .system.service import ResetService
from .watchlist.repository import WatchlistRepository
from .watchlist.service import WatchlistService

if TYPE_CHECKING:
    from .history import HistoryStore
    from .portfolio.service import TradeService


async def get_current_user(request: Request, response: Response) -> User:
    """Resolve the caller, minting and seeding a guest when there is none.

    A cookie that does not verify -- tampered, signed with a rotated secret,
    or pointing at a row a database reset removed -- is treated exactly like
    no cookie at all. Handing back a 401 would be wrong: there is nothing to
    log in to yet, and the honest answer to an unreadable session is a fresh
    one.

    The cookie is re-issued on every resolve, not only on a mint. Both the
    signature timestamp and the browser's `Max-Age` are absolute, so a cookie
    written once expired 90 days later no matter how active its owner was --
    a user who visited every single day was silently handed a fresh guest and
    a fresh $10,000 on day 90, their real row orphaned. Refreshing it on
    every request is a sliding window with no threshold to reason about: the
    session always has its full life left as of the last request. It costs a
    `Set-Cookie` header on every response, which is the cheapest part of any
    of these responses.
    """
    store: UserStore = request.app.state.user_store
    cookie: SessionCookie = request.app.state.session_cookie

    user_id = cookie.verify(request.cookies.get(COOKIE_NAME))
    user = await store.get(user_id) if user_id else None

    if user is None:
        user = await store.mint_guest()
        # A minted guest arrives with ten seeded watchlist rows the market
        # source has never heard of. Without this the feed keeps whatever it
        # was tracking -- nothing at all, on an instance that started against
        # an empty database -- and the new user sees a watchlist with no
        # prices in it. Reconciling here also repairs a source that has
        # drifted from the database for any other reason.
        await request.app.state.reconciler.reconcile()
    else:
        await store.touch(user)

    _set_session_cookie(request, response, cookie, user.id)
    return user


def _request_is_https(request: Request) -> bool:
    """Whether the *browser* reached us over https.

    `X-Forwarded-Proto` first, because Vercel and every other TLS-terminating
    proxy speaks plain http to the app behind it -- `request.url.scheme` is
    `http` there even though the browser is on https. A proxy chain sends a
    comma-separated list, oldest first, and the first entry is the one the
    browser actually used.

    That header is client-controlled on a direct connection, and trusting it
    is deliberate: the only thing it decides is whether *this* response's
    cookie carries `Secure`. Forging `https` over plain http makes the
    forger's own cookie undeliverable to themselves and reaches nobody else,
    so there is nothing here to escalate. It is not an authorization input.
    """
    forwarded = request.headers.get("x-forwarded-proto")
    scheme = forwarded.split(",")[0].strip() if forwarded else request.url.scheme
    return scheme.lower() == "https"


def _set_session_cookie(
    request: Request, response: Response, cookie: SessionCookie, user_id: str
) -> None:
    """Attach the session cookie.

    `Secure` follows the scheme, not the hostname. Keying it off the hostname
    ("everything except localhost is secure") looks plausible and is wrong: a
    browser refuses to store or return a Secure cookie over plain http, so a
    Docker deployment reached on a LAN address -- http://192.168.1.5:8000 --
    would drop the cookie on every response and mint a fresh guest on every
    single request. Unbounded rows, a portfolio that resets constantly, and
    nothing raising.
    """
    response.set_cookie(
        key=COOKIE_NAME,
        value=cookie.sign(user_id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=_request_is_https(request),
        path="/",
    )
    # Parked on the request so the error handlers can re-attach it. They build
    # a fresh JSONResponse, which does not inherit this dependency
    # sub-response's headers, so without this every 4xx and 422 on a
    # cookie-less first request minted a guest -- twelve rows -- and handed the
    # browser no session to come back with. The next request minted another.
    setattr(request.state, PENDING_SESSION_COOKIE_ATTR, response.headers.get("set-cookie"))


CurrentUserDep = Annotated["User", Depends(get_current_user)]


def get_trade_service(request: Request, user: CurrentUserDep) -> TradeService:
    """Build a TradeService scoped to the calling user.

    Per-request construction is what makes the user id a required argument
    everywhere below it. The pool, price cache, source, reconciler and locks
    are shared; only the repositories are per-user.
    """
    state = request.app.state
    return build_trade_service(
        state.db,
        state.settings,
        state.price_cache,
        user.id,
        reconciler=state.reconciler,
        lock=state.trade_lock,
    )


TradeServiceDep = Annotated["TradeService", Depends(get_trade_service)]


def get_watchlist_service(request: Request, user: CurrentUserDep) -> WatchlistService:
    state = request.app.state
    return WatchlistService(
        state.db,
        WatchlistRepository(state.db, user.id),
        state.reconciler,
        state.watchlist_lock,
        state.settings.watchlist_cap,
    )


WatchlistServiceDep = Annotated["WatchlistService", Depends(get_watchlist_service)]


def get_chat_service(
    request: Request,
    user: CurrentUserDep,
    trades: TradeServiceDep,
    watchlist: WatchlistServiceDep,
) -> ChatService:
    """Depends on the two service dependencies rather than rebuilding them, so
    a chat-driven trade goes through the same locked service a manual one does.
    """
    state = request.app.state
    return ChatService(
        ChatRepository(state.db, user.id),
        trades,
        watchlist,
        state.chat_client,
        ActionExecutor(trades, watchlist),
        state.settings,
    )


ChatServiceDep = Annotated["ChatService", Depends(get_chat_service)]


def get_reset_service(request: Request, user: CurrentUserDep) -> ResetService:
    """Build a ResetService that can only wipe the caller's own rows."""
    state = request.app.state
    return ResetService(
        state.db,
        state.settings,
        user.id,
        state.reconciler,
        state.trade_lock,
        state.watchlist_lock,
    )


ResetServiceDep = Annotated["ResetService", Depends(get_reset_service)]


def get_history_store(request: Request) -> HistoryStore:
    return request.app.state.history_store


HistoryStoreDep = Annotated["HistoryStore", Depends(get_history_store)]
