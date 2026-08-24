"""Portfolio HTTP routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from ..deps import CurrentUserDep, TradeServiceDep

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

#: Upper bound on history points, so a long-running container cannot be asked
#: for an unbounded array.
MAX_HISTORY_LIMIT = 5000


class TradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    side: Literal["buy", "sell"]
    quantity: float


@router.get("")
async def get_portfolio(request: Request, service: TradeServiceDep, user: CurrentUserDep) -> dict:
    """Current cash, positions priced live, and totals."""
    # `user` is resolved for its side effects here -- minting a guest and
    # setting the session cookie. Task 6 scopes the service to it.
    del user
    if request.app.state.settings.serverless:
        # No background task runs between requests on a serverless
        # deployment, so the periodic snapshot moves onto the read that is
        # naturally scoped to a user who is actually looking at the app.
        await service.write_snapshot_if_stale()
    view = await service.get_portfolio()
    return view.to_dict()


@router.post("/trade")
async def execute_trade(body: TradeRequest, service: TradeServiceDep, user: CurrentUserDep) -> dict:
    """Execute a market order at the current cached price."""
    # `user` is resolved for its side effects here -- minting a guest and
    # setting the session cookie. Task 6 scopes the service to it.
    del user
    result = await service.execute_trade(body.ticker, body.side, body.quantity)
    return result.to_dict()


@router.get("/history")
async def get_history(
    service: TradeServiceDep,
    user: CurrentUserDep,
    limit: Annotated[int, Query(ge=1, le=MAX_HISTORY_LIMIT)] = 500,
) -> dict:
    """Portfolio value snapshots over time, oldest first."""
    # `user` is resolved for its side effects here -- minting a guest and
    # setting the session cookie. Task 6 scopes the service to it.
    del user
    snapshots = await service.get_history(limit=limit)
    return {"snapshots": [s.to_dict() for s in snapshots]}
