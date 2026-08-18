"""Chat and LLM action models."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field


class TradeAction(BaseModel):
    """A trade the model wants executed."""

    ticker: str
    side: Literal["buy", "sell"]
    quantity: float


class WatchlistAction(BaseModel):
    """A watchlist change the model wants applied."""

    ticker: str
    action: Literal["add", "remove"]


class ChatCompletionSchema(BaseModel):
    """The structured response the model must return.

    Mirrors PLAN §9's schema exactly. Both action lists default to empty so a
    plain conversational reply is valid without them.
    """

    message: str = Field(description="The conversational response shown to the user")
    trades: list[TradeAction] = Field(default_factory=list)
    watchlist_changes: list[WatchlistAction] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class ExecutedAction:
    """The outcome of one action the model requested.

    Actions execute independently, so a batch can be part success and part
    failure; each carries its own status.
    """

    kind: Literal["trade", "watchlist"]
    ticker: str
    status: Literal["ok", "error"]
    detail: dict
    error_code: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "ticker": self.ticker,
            "status": self.status,
            "detail": self.detail,
            "error_code": self.error_code,
            "error_message": self.error_message,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ExecutedAction:
        return cls(
            kind=data["kind"],
            ticker=data["ticker"],
            status=data["status"],
            detail=data.get("detail") or {},
            error_code=data.get("error_code"),
            error_message=data.get("error_message"),
        )


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A stored conversation message."""

    id: str
    role: Literal["user", "assistant"]
    content: str
    actions: list[ExecutedAction] | None
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "role": self.role,
            "content": self.content,
            "actions": [a.to_dict() for a in self.actions] if self.actions is not None else None,
            "created_at": self.created_at,
        }

    @staticmethod
    def serialize_actions(actions: list[ExecutedAction] | None) -> str | None:
        return json.dumps([a.to_dict() for a in actions]) if actions is not None else None

    @staticmethod
    def deserialize_actions(raw: str | None) -> list[ExecutedAction] | None:
        if raw is None:
            return None
        return [ExecutedAction.from_dict(item) for item in json.loads(raw)]


@dataclass(frozen=True, slots=True)
class ChatReply:
    """The response returned by POST /api/chat."""

    message: str
    actions: list[ExecutedAction]
    error: bool = False

    def to_dict(self) -> dict:
        return {
            "message": self.message,
            "actions": [a.to_dict() for a in self.actions],
            "error": self.error,
        }
