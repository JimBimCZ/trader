"""Tests for the chat turn orchestration."""

from __future__ import annotations

from unittest.mock import patch

from app.errors import LLMError
from app.llm.service import FAILURE_MESSAGE


class TestSendMessage:
    async def test_stores_both_sides_of_the_turn(self, services):
        await services.chat_service.send_message("hello")
        history = await services.chat_service.list_history()
        assert [m.role for m in history] == ["user", "assistant"]

    async def test_executes_the_requested_trade(self, services):
        await services.track("AAPL", price=190.0)
        reply = await services.chat_service.send_message("buy 10 AAPL")

        assert reply.error is False
        assert reply.actions[0].status == "ok"
        assert (await services.positions.get("AAPL")).quantity == 10

    async def test_records_actions_against_the_assistant_message(self, services):
        await services.track("AAPL", price=190.0)
        await services.chat_service.send_message("buy 1 AAPL")

        history = await services.chat_service.list_history()
        assert history[-1].actions[0].kind == "trade"
        assert history[0].actions is None

    async def test_portfolio_context_reaches_the_model(self, services):
        """The prompt carries real balances, so replies quote real numbers."""
        captured = {}

        async def capture(messages):
            captured["messages"] = messages
            from app.llm.models import ChatCompletionSchema

            return ChatCompletionSchema(message="ok")

        with patch.object(services.chat_client, "complete", side_effect=capture):
            await services.chat_service.send_message("how is my portfolio?")

        context = captured["messages"][1]["content"]
        assert "10,000.00" in context

    async def test_prior_history_is_included(self, services):
        captured = {}

        async def capture(messages):
            captured["messages"] = messages
            from app.llm.models import ChatCompletionSchema

            return ChatCompletionSchema(message="ok")

        await services.chat_service.send_message("first message")
        with patch.object(services.chat_client, "complete", side_effect=capture):
            await services.chat_service.send_message("second message")

        contents = [m["content"] for m in captured["messages"]]
        assert "first message" in contents
        assert contents[-1] == "second message"

    async def test_the_new_message_is_not_duplicated_in_history(self, services):
        """The turn being sent must appear once, as the final message."""
        captured = {}

        async def capture(messages):
            captured["messages"] = messages
            from app.llm.models import ChatCompletionSchema

            return ChatCompletionSchema(message="ok")

        with patch.object(services.chat_client, "complete", side_effect=capture):
            await services.chat_service.send_message("only once")

        assert [m["content"] for m in captured["messages"]].count("only once") == 1


class TestFailureHandling:
    async def test_an_llm_failure_returns_a_friendly_message(self, services):
        """Upstream failure never becomes an HTTP error for the chat panel."""
        with patch.object(services.chat_client, "complete", side_effect=LLMError("down")):
            reply = await services.chat_service.send_message("hello")

        assert reply.error is True
        assert reply.message == FAILURE_MESSAGE
        assert reply.actions == []

    async def test_a_failed_turn_is_still_stored(self, services):
        with patch.object(services.chat_client, "complete", side_effect=LLMError("down")):
            await services.chat_service.send_message("hello")

        history = await services.chat_service.list_history()
        assert history[-1].content == FAILURE_MESSAGE

    async def test_a_failed_turn_changes_no_positions(self, services):
        with patch.object(services.chat_client, "complete", side_effect=LLMError("down")):
            await services.chat_service.send_message("buy 10 AAPL")
        assert await services.positions.list() == []


class TestHistory:
    async def test_returns_messages_oldest_first(self, services):
        await services.chat_service.send_message("one")
        await services.chat_service.send_message("two")
        history = await services.chat_service.list_history()
        assert [m.content for m in history][:3] == ["one", history[1].content, "two"]

    async def test_respects_the_limit(self, services):
        for i in range(4):
            await services.chat_service.send_message(f"message {i}")
        assert len(await services.chat_service.list_history(limit=3)) == 3

    async def test_actions_survive_a_round_trip_through_the_database(self, services):
        """Stored action JSON deserializes back into the same structure."""
        await services.track("AAPL", price=190.0)
        await services.chat_service.send_message("buy 2 AAPL")

        history = await services.chat_service.list_history()
        action = history[-1].actions[0]
        assert action.kind == "trade"
        assert action.ticker == "AAPL"
        assert action.detail["quantity"] == 2.0
