"""Chat HTTP routes."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from ..deps import ChatServiceDep

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.get("")
async def get_history(
    service: ChatServiceDep,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
) -> dict:
    """Conversation history, oldest first."""
    messages = await service.list_history(limit=limit)
    return {"messages": [m.to_dict() for m in messages]}


@router.post("")
async def send_message(body: ChatRequest, service: ChatServiceDep) -> dict:
    reply = await service.send_message(body.message)
    return reply.to_dict()
