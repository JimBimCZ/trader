"""Tests for the live chat client, with the network mocked out."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.errors import LLMError
from app.llm.client import LiveChatClient

VALID = json.dumps({"message": "Hello", "trades": [], "watchlist_changes": []})


def response_with(content: str) -> MagicMock:
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = content
    return response


class TestComplete:
    async def test_parses_a_valid_structured_response(self):
        with patch("app.llm.client.completion", return_value=response_with(VALID)) as mock:
            result = await LiveChatClient("key").complete([{"role": "user", "content": "hi"}])
        assert result.message == "Hello"
        assert mock.call_count == 1

    async def test_requests_structured_output_via_cerebras(self):
        """The provider order and response schema must reach litellm."""
        with patch("app.llm.client.completion", return_value=response_with(VALID)) as mock:
            await LiveChatClient("key").complete([{"role": "user", "content": "hi"}])

        kwargs = mock.call_args.kwargs
        assert kwargs["extra_body"] == {"provider": {"order": ["cerebras"]}}
        assert kwargs["response_format"].__name__ == "ChatCompletionSchema"
        assert kwargs["model"] == "openrouter/openai/gpt-oss-120b"

    async def test_parses_trades_out_of_the_response(self):
        payload = json.dumps(
            {
                "message": "Bought",
                "trades": [{"ticker": "AAPL", "side": "buy", "quantity": 10}],
                "watchlist_changes": [],
            }
        )
        with patch("app.llm.client.completion", return_value=response_with(payload)):
            result = await LiveChatClient("key").complete([{"role": "user", "content": "hi"}])
        assert result.trades[0].ticker == "AAPL"


class TestRepairRetry:
    async def test_retries_once_on_malformed_json(self):
        """A single repair attempt recovers from a chatty response."""
        with patch(
            "app.llm.client.completion",
            side_effect=[response_with("not json at all"), response_with(VALID)],
        ) as mock:
            result = await LiveChatClient("key").complete([{"role": "user", "content": "hi"}])
        assert result.message == "Hello"
        assert mock.call_count == 2

    async def test_gives_up_after_the_repair_also_fails(self):
        with patch(
            "app.llm.client.completion",
            side_effect=[response_with("nope"), response_with("still nope")],
        ) as mock:
            with pytest.raises(LLMError):
                await LiveChatClient("key").complete([{"role": "user", "content": "hi"}])
        assert mock.call_count == 2


class TestFailures:
    async def test_an_empty_response_is_an_error(self):
        with patch("app.llm.client.completion", return_value=response_with("")):
            with pytest.raises(LLMError):
                await LiveChatClient("key").complete([{"role": "user", "content": "hi"}])

    async def test_a_transport_failure_becomes_an_llm_error(self):
        """Network errors never escape as raw exceptions."""
        with patch("app.llm.client.completion", side_effect=ConnectionError("down")):
            with pytest.raises(LLMError):
                await LiveChatClient("key").complete([{"role": "user", "content": "hi"}])

    async def test_a_timeout_becomes_an_llm_error(self):
        import time

        with patch("app.llm.client.completion", side_effect=lambda **_: time.sleep(0.5)):
            with pytest.raises(LLMError, match="too long"):
                await LiveChatClient("key", timeout=0.05).complete(
                    [{"role": "user", "content": "hi"}]
                )
