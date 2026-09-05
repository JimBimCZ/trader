"""Portfolio HTTP routes."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field

from ..deps import TradeServiceDep

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

#: Upper bound on history points, so a long-running container cannot be asked
#: for an unbounded array.
MAX_HISTORY_LIMIT = 5000


class TradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=16)
    side: Literal["buy", "sell"]
    quantity: float


@router.get("")
async def get_portfolio(request: Request, service: TradeServiceDep) -> dict:
    """Current cash, positions priced live, and totals."""
    if request.app.state.settings.serverless:
        # No background task runs between requests on a serverless
        # deployment, so the periodic snapshot moves onto the read that is
        # naturally scoped to a user who is actually looking at the app.
        await service.write_snapshot_if_stale()
    view = await service.get_portfolio()
    return view.to_dict()


@router.post("/trade")
async def execute_trade(body: TradeRequest, service: TradeServiceDep) -> dict:
    """Execute a market order at the current cached price."""
    result = await service.execute_trade(body.ticker, body.side, body.quantity)
    return result.to_dict()


@router.get("/history")
async def get_history(
    service: TradeServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_HISTORY_LIMIT)] = 500,
) -> dict:
    """Portfolio value snapshots over time, oldest first."""
    snapshots = await service.get_history(limit=limit)
    return {"snapshots": [s.to_dict() for s in snapshots]}


#: Upper bound on trade rows returned in one call.
MAX_TRADES_LIMIT = 500


@router.get("/trades")
async def get_trades(
    service: TradeServiceDep,
    limit: Annotated[int, Query(ge=1, le=MAX_TRADES_LIMIT)] = 200,
) -> dict:
    """Executed trades, newest first, with realized P&L on each sale."""
    return {"trades": await service.get_trades(limit=limit)}
