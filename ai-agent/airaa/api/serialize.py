"""JSON shapes for conversations, shared by the owner view and the share views."""
from __future__ import annotations

from datetime import timedelta
from typing import Any, Dict


def conversation_json(session: Dict[str, Any], session_id: str, redact_research_data: bool = False) -> Dict[str, Any]:
    base = session["created_at"]
    messages = []
    for i, msg in enumerate(session["chat_history"].messages):
        extra = getattr(msg, "additional_kwargs", {}) or {}
        is_ai = msg.type == "ai"
        item = {
            "type": "ai" if is_ai else "human",
            "content": msg.content,
            "timestamp": extra.get("timestamp") or (base + timedelta(minutes=i)).isoformat(),
        }
        if is_ai and extra.get("research_data") and not redact_research_data:
            item["research_data"] = extra["research_data"]
        messages.append(item)
    return {
        "success": True,
        "session_id": session_id,
        "messages": messages,
        "message_count": len(messages),
        "created_at": session["created_at"].isoformat(),
        "last_activity": session["last_activity"].isoformat(),
    }
