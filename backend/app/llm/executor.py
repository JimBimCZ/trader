"""Executes the actions an LLM response requests."""

from __future__ import annotations

import logging

from ..errors import AppError
from ..portfolio.service import TradeService
from ..watchlist.service import WatchlistService
from .models import ChatCompletionSchema, ExecutedAction

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Runs trades and watchlist changes, each independently.

    A failure in one action never blocks the others: if the model asks for
    three trades and the second is unaffordable, the first and third still
    execute and all three outcomes are reported.
    """

    def __init__(self, trade_service: TradeService, watchlist_service: WatchlistService) -> None:
        self._trades = trade_service
        self._watchlist = watchlist_service

    async def execute(self, response: ChatCompletionSchema) -> list[ExecutedAction]:
        results: list[ExecutedAction] = []

        for trade in response.trades:
            results.append(await self._execute_trade(trade))
        for change in response.watchlist_changes:
            results.append(await self._execute_watchlist_change(change))

        return results

    async def _execute_trade(self, action) -> ExecutedAction:
        ticker = action.ticker.strip().upper()
        try:
            result = await self._trades.execute_trade(action.ticker, action.side, action.quantity)
        except AppError as exc:
            logger.info("LLM trade rejected: %s %s — %s", action.side, ticker, exc.message)
            return ExecutedAction(
                kind="trade",
                ticker=ticker,
                status="error",
                detail={"side": action.side, "quantity": action.quantity},
                error_code=exc.code,
                error_message=exc.message,
            )
        return ExecutedAction(
            kind="trade",
            ticker=ticker,
            status="ok",
            detail={
                "side": result.trade.side,
                "quantity": result.trade.quantity,
                "price": result.trade.price,
            },
        )

    async def _execute_watchlist_change(self, action) -> ExecutedAction:
        ticker = action.ticker.strip().upper()
        try:
            if action.action == "add":
                await self._watchlist.add(action.ticker)
            else:
                await self._watchlist.remove(action.ticker)
        except AppError as exc:
            logger.info(
                "LLM watchlist change rejected: %s %s — %s", action.action, ticker, exc.message
            )
            return ExecutedAction(
                kind="watchlist",
                ticker=ticker,
                status="error",
                detail={"action": action.action},
                error_code=exc.code,
                error_message=exc.message,
            )
        return ExecutedAction(
            kind="watchlist", ticker=ticker, status="ok", detail={"action": action.action}
        )
