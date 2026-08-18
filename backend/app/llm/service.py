"""Chat orchestration: context, model call, action execution, persistence."""

from __future__ import annotations

import logging

from ..config import Settings
from ..errors import LLMError
from ..portfolio.service import TradeService
from ..watchlist.service import WatchlistService
from .client import ChatClient
from .executor import ActionExecutor
from .models import ChatMessage, ChatReply
from .prompt import build_context_block, build_messages

logger = logging.getLogger(__name__)

FAILURE_MESSAGE = (
    "I'm having trouble reaching the AI assistant right now. Your portfolio is unchanged."
)


class ChatService:
    """Runs one conversational turn end to end."""

    def __init__(
        self,
        repo,
        trade_service: TradeService,
        watchlist_service: WatchlistService,
        client: ChatClient,
        executor: ActionExecutor,
        settings: Settings,
    ) -> None:
        self._repo = repo
        self._trades = trade_service
        self._watchlist = watchlist_service
        self._client = client
        self._executor = executor
        self._settings = settings

    async def list_history(self, limit: int = 50) -> list[ChatMessage]:
        """Stored conversation, oldest first."""
        return await self._repo.list_recent(limit=limit)

    async def send_message(self, user_message: str) -> ChatReply:
        """Handle one user turn.

        An upstream failure is never surfaced as an HTTP error: the user gets
        a normal assistant message carrying error=true, so the chat panel
        needs no separate error path.
        """
        # Read history before storing this turn: the new message is the
        # prompt's final entry, not part of the prior conversation.
        history = await self._repo.list_recent(limit=self._settings.chat_history_limit)
        await self._repo.add("user", user_message)

        portfolio = await self._trades.get_portfolio()
        watchlist = await self._watchlist.list()

        messages = build_messages(
            context_block=build_context_block(portfolio, watchlist),
            history=history,
            user_message=user_message,
            char_budget=self._settings.chat_history_char_budget,
        )

        try:
            response = await self._client.complete(messages)
        except LLMError as exc:
            logger.warning("Chat turn failed: %s", exc.message)
            await self._repo.add("assistant", FAILURE_MESSAGE, actions=[])
            return ChatReply(message=FAILURE_MESSAGE, actions=[], error=True)

        actions = await self._executor.execute(response)
        await self._repo.add("assistant", response.message, actions=actions)
        return ChatReply(message=response.message, actions=actions, error=False)
