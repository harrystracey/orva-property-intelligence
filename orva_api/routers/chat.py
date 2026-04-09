"""
HLM Chat API — SSE-based AI property intelligence chat.
"""

import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from ..auth import get_current_user
from ..deps import get_data_store, DataStore
from ..schemas.chat import ChatSendRequest, ChatListResponse, ChatListItem, ChatHistoryResponse, ChatMessage
from ..services.chat_service import run_chat, list_chats, load_chat, create_chat, delete_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.post("/send")
async def send_message(
    req: ChatSendRequest,
    user: dict = Depends(get_current_user),
    ds: DataStore = Depends(get_data_store),
):
    """Send a message to HLM. Returns SSE stream with status updates and final response."""
    username = user["username"]

    async def event_stream():
        # run_chat is a sync generator — iterate in a thread
        def _run():
            return list(run_chat(req.message, req.chat_id, username, ds))

        events = await asyncio.to_thread(_run)
        for event in events:
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/list", response_model=ChatListResponse)
async def get_chat_list(
    user: dict = Depends(get_current_user),
):
    """List all chats for the current user."""
    username = user["username"]
    chats = list_chats(username)
    return ChatListResponse(
        chats=[ChatListItem(**c) for c in chats]
    )


@router.get("/{chat_id}/history", response_model=ChatHistoryResponse)
async def get_chat_history(
    chat_id: str,
    user: dict = Depends(get_current_user),
):
    """Load a conversation's messages."""
    username = user["username"]
    chat = load_chat(username, chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return ChatHistoryResponse(
        chat_id=chat["id"],
        name=chat.get("name", "Untitled"),
        messages=[
            ChatMessage(
                role=m["role"],
                content=m["content"],
                timestamp=m.get("timestamp"),
            )
            for m in chat.get("messages", [])
        ],
    )


@router.post("/new")
async def new_chat(
    user: dict = Depends(get_current_user),
):
    """Create a new empty chat."""
    username = user["username"]
    chat = create_chat(username)
    return {"chat_id": chat["id"]}


@router.delete("/{chat_id}")
async def remove_chat(
    chat_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete a chat."""
    username = user["username"]
    deleted = delete_chat(username, chat_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"status": "deleted"}
