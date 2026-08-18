"""Tests for independent execution of LLM-requested actions."""

from __future__ import annotations

from app.llm.models import ChatCompletionSchema, TradeAction, WatchlistAction


class TestTradeActions:
    async def test_executes_a_valid_trade(self, services):
        await services.track("AAPL", price=190.0)
        actions = await services.executor.execute(
            ChatCompletionSchema(
                message="ok", trades=[TradeAction(ticker="AAPL", side="buy", quantity=2)]
            )
        )
        assert actions[0].status == "ok"
        assert actions[0].detail["price"] == 190.0

    async def test_records_a_rejected_trade_without_raising(self, services):
        """A failed trade is reported, not thrown, so the chat still replies."""
        await services.track("AAPL", price=190.0)
        actions = await services.executor.execute(
            ChatCompletionSchema(
                message="ok", trades=[TradeAction(ticker="AAPL", side="buy", quantity=10_000)]
            )
        )
        assert actions[0].status == "error"
        assert actions[0].error_code == "INSUFFICIENT_CASH"

    async def test_one_failure_does_not_block_the_others(self, services):
        """The documented partial-failure behavior: each action stands alone."""
        await services.track("AAPL", "MSFT", price=100.0)
        actions = await services.executor.execute(
            ChatCompletionSchema(
                message="ok",
                trades=[
                    TradeAction(ticker="AAPL", side="buy", quantity=1),
                    TradeAction(ticker="AAPL", side="buy", quantity=10_000),
                    TradeAction(ticker="MSFT", side="buy", quantity=1),
                ],
            )
        )
        assert [a.status for a in actions] == ["ok", "error", "ok"]
        assert await services.positions.get("MSFT") is not None

    async def test_an_invalid_ticker_is_reported_per_action(self, services):
        actions = await services.executor.execute(
            ChatCompletionSchema(
                message="ok", trades=[TradeAction(ticker="BRK.B", side="buy", quantity=1)]
            )
        )
        assert actions[0].error_code == "INVALID_TICKER"


class TestWatchlistActions:
    async def test_adds_a_ticker(self, services):
        actions = await services.executor.execute(
            ChatCompletionSchema(
                message="ok", watchlist_changes=[WatchlistAction(ticker="PYPL", action="add")]
            )
        )
        assert actions[0].status == "ok"
        assert "PYPL" in await services.watchlist_service.list()

    async def test_removes_a_ticker(self, services):
        actions = await services.executor.execute(
            ChatCompletionSchema(
                message="ok", watchlist_changes=[WatchlistAction(ticker="AAPL", action="remove")]
            )
        )
        assert actions[0].status == "ok"
        assert "AAPL" not in await services.watchlist_service.list()

    async def test_removing_an_absent_ticker_is_reported(self, services):
        actions = await services.executor.execute(
            ChatCompletionSchema(
                message="ok", watchlist_changes=[WatchlistAction(ticker="PYPL", action="remove")]
            )
        )
        assert actions[0].status == "error"
        assert actions[0].error_code == "TICKER_NOT_FOUND"


class TestMixed:
    async def test_trades_and_watchlist_changes_both_run(self, services):
        await services.track("AAPL", price=190.0)
        actions = await services.executor.execute(
            ChatCompletionSchema(
                message="ok",
                trades=[TradeAction(ticker="AAPL", side="buy", quantity=1)],
                watchlist_changes=[WatchlistAction(ticker="PYPL", action="add")],
            )
        )
        assert [a.kind for a in actions] == ["trade", "watchlist"]

    async def test_no_actions_returns_an_empty_list(self, services):
        assert await services.executor.execute(ChatCompletionSchema(message="just talking")) == []
