"""Factory selecting the live or mock chat client.

Mirrors create_market_data_source: one env-driven decision, made once.
"""

from __future__ import annotations

import logging

from ..config import Settings
from .client import ChatClient, LiveChatClient
from .mock_client import MockChatClient

logger = logging.getLogger(__name__)


def create_chat_client(settings: Settings) -> ChatClient:
    """Return the mock client when LLM_MOCK is set, otherwise the live one."""
    if settings.llm_mock:
        logger.info("Chat client: deterministic mock")
        return MockChatClient()
    if not settings.openrouter_api_key.strip():
        logger.warning("OPENROUTER_API_KEY is not set; falling back to the mock chat client")
        return MockChatClient()
    logger.info("Chat client: OpenRouter via Cerebras (%s)", "openrouter/openai/gpt-oss-120b")
    return LiveChatClient(api_key=settings.openrouter_api_key, timeout=settings.llm_timeout_seconds)
