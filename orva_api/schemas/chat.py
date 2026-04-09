"""Pydantic models for the HLM chat endpoints."""

from pydantic import BaseModel


class ChatSendRequest(BaseModel):
    message: str
    chat_id: str | None = None


class ChatListItem(BaseModel):
    id: str
    name: str
    last_updated: str
    message_count: int


class ChatListResponse(BaseModel):
    chats: list[ChatListItem]


class ChatMessage(BaseModel):
    role: str
    content: str
    timestamp: str | None = None


class ChatHistoryResponse(BaseModel):
    chat_id: str
    name: str
    messages: list[ChatMessage]
