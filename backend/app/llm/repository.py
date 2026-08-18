"""Chat message persistence."""

from __future__ import annotations

import uuid
from typing import Literal

from ..clock import utcnow_iso
from ..db import DEFAULT_USER_ID, Database
from .models import ChatMessage, ExecutedAction


class ChatRepository:
    """Conversation history. Persisted so a reload does not lose the thread."""

    def __init__(self, db: Database, user_id: str = DEFAULT_USER_ID) -> None:
        self._db = db
        self._user_id = user_id

    async def add(
        self,
        role: Literal["user", "assistant"],
        content: str,
        actions: list[ExecutedAction] | None = None,
    ) -> ChatMessage:
        message = ChatMessage(
            id=str(uuid.uuid4()),
            role=role,
            content=content,
            actions=actions,
            created_at=utcnow_iso(),
        )
        await self._db.execute(
            """
            INSERT INTO chat_messages (id, user_id, role, content, actions, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                self._user_id,
                message.role,
                message.content,
                ChatMessage.serialize_actions(actions),
                message.created_at,
            ),
        )
        await self._db.commit()
        return message

    async def list_recent(self, limit: int = 50) -> list[ChatMessage]:
        """The newest `limit` messages, returned oldest-first for display."""
        rows = await self._db.fetch_all(
            """
            SELECT id, role, content, actions, created_at
            FROM chat_messages WHERE user_id = ?
            ORDER BY created_at DESC, rowid DESC
            LIMIT ?
            """,
            (self._user_id, limit),
        )
        return [
            ChatMessage(
                id=row["id"],
                role=row["role"],
                content=row["content"],
                actions=ChatMessage.deserialize_actions(row["actions"]),
                created_at=row["created_at"],
            )
            for row in reversed(rows)
        ]

    async def delete_all(self) -> None:
        await self._db.execute("DELETE FROM chat_messages WHERE user_id = ?", (self._user_id,))
