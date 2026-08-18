"""LLM client: the live OpenRouter/Cerebras path and its abstract contract."""

from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod

from litellm import completion
from pydantic import ValidationError

from ..errors import LLMError
from .models import ChatCompletionSchema

logger = logging.getLogger(__name__)

MODEL = "openrouter/openai/gpt-oss-120b"
EXTRA_BODY = {"provider": {"order": ["cerebras"]}}

_REPAIR_INSTRUCTION = (
    "Your previous response was not valid JSON matching the required schema. "
    "Respond again with ONLY the JSON object, no prose and no code fences."
)


class ChatClient(ABC):
    """Contract shared by the live client and the deterministic mock."""

    @abstractmethod
    async def complete(self, messages: list[dict]) -> ChatCompletionSchema:
        """Return the model's structured response.

        Raises LLMError on any unrecoverable failure. Callers translate that
        into a friendly in-conversation message rather than an HTTP error.
        """


class LiveChatClient(ChatClient):
    """Calls the model via LiteLLM -> OpenRouter with Cerebras as provider.

    litellm.completion is synchronous, so it runs in a worker thread to keep
    the event loop free for the price stream.
    """

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    async def complete(self, messages: list[dict]) -> ChatCompletionSchema:
        raw = await self._call(messages)
        try:
            return ChatCompletionSchema.model_validate_json(raw)
        except (ValidationError, ValueError):
            logger.warning("Model returned unparseable JSON; attempting one repair retry")

        repair = [*messages, {"role": "system", "content": _REPAIR_INSTRUCTION}]
        raw = await self._call(repair)
        try:
            return ChatCompletionSchema.model_validate_json(raw)
        except (ValidationError, ValueError) as exc:
            raise LLMError("The assistant returned a malformed response.") from exc

    async def _call(self, messages: list[dict]) -> str:
        """One structured-output completion, with a timeout."""
        try:
            response = await asyncio.wait_for(
                asyncio.to_thread(self._completion, messages), timeout=self._timeout
            )
        except TimeoutError as exc:
            raise LLMError("The assistant took too long to respond.") from exc
        except Exception as exc:
            logger.exception("LLM call failed")
            raise LLMError("Could not reach the assistant.") from exc

        content = response.choices[0].message.content
        if not content:
            raise LLMError("The assistant returned an empty response.")
        return content

    def _completion(self, messages: list[dict]):
        return completion(
            model=MODEL,
            messages=messages,
            response_format=ChatCompletionSchema,
            reasoning_effort="low",
            extra_body=EXTRA_BODY,
            api_key=self._api_key,
        )
