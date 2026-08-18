"""LLM chat integration.

Public API:
    ChatService        - runs one conversational turn end to end
    create_chat_client - selects the live or mock client from settings
    ChatRepository     - conversation persistence
    ActionExecutor     - executes the actions a response requests
"""

from __future__ import annotations

from .executor import ActionExecutor
from .factory import create_chat_client
from .repository import ChatRepository
from .service import ChatService

__all__ = ["ActionExecutor", "ChatRepository", "ChatService", "create_chat_client"]
