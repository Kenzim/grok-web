"""JSON views of grokbot models and events. Never include protobuf `.raw`."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from grokbot.events import Message, WidgetRequest
from grokbot.models import Account, Agent, SendReceipt, TranscriptEntry
from grokbot.transcripts import events_from_entry


def json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8")
        except UnicodeDecodeError:
            return None
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(v) for v in value]
    if is_dataclass(value) and not isinstance(value, type):
        data = asdict(value)
        data.pop("raw", None)
        data.pop("live_state", None)
        return json_safe(data)
    if hasattr(value, "DESCRIPTOR"):
        return None
    return str(value)


def account_json(account: Account) -> dict[str, Any]:
    return {
        "user_id": account.user_id,
        "email": account.email,
        "first_name": account.first_name,
        "auth_id": account.auth_id,
    }


def agent_json(agent: Agent) -> dict[str, Any]:
    return {
        "id": agent.id,
        "agent_id": agent.agent_id,
        "name": agent.name,
        "description": agent.description,
        "harness": agent.harness,
        "kind": agent.kind,
        "created_at_ms": agent.created_at_ms,
        "title": agent.title,
        "viewer_session_id": agent.viewer_session_id,
    }


def receipt_json(receipt: SendReceipt) -> dict[str, Any]:
    return {
        "message_id": receipt.message_id,
        "dispatched": receipt.dispatched,
        "delivery": receipt.delivery,
        "workflow_id": receipt.workflow_id,
    }


def _images_from_body(body: Any) -> list[dict[str, str]]:
    src = body
    if isinstance(body, dict):
        msg = body.get("message")
        if isinstance(msg, dict):
            src = msg
    if not isinstance(src, dict):
        return []
    out: list[dict[str, str]] = []
    for item in src.get("images") or []:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or item.get("src") or "")
        if not url or url.startswith("file:"):
            continue
        out.append({"url": url, "alt": str(item.get("alt") or "")})
    return out


def widget_json(event: WidgetRequest) -> dict[str, Any]:
    return {
        "agent_id": event.agent_id,
        "session_id": event.session_id,
        "entry_id": event.entry_id,
        "kind": event.kind,
        "prompt": event.prompt,
        "request_id": event.request_id,
        "body": json_safe(event.body),
    }


def entry_json(agent_id: str, session_id: str, entry: TranscriptEntry) -> dict[str, Any]:
    payload = {
        "seq": entry.seq,
        "entry_id": entry.entry_id,
        "entry_kind": entry.entry_kind,
        "body": json_safe(entry.body),
        "updated_seq": entry.updated_seq,
        "text": "",
        "role": "",
        "ts": 0.0,
        "images": _images_from_body(entry.body),
        "widget": None,
    }
    for event in events_from_entry(agent_id, session_id, entry):
        if isinstance(event, WidgetRequest):
            payload["widget"] = widget_json(event)
        elif isinstance(event, Message):
            payload["text"] = event.text
            payload["role"] = event.role
            payload["ts"] = event.ts
    return payload


def event_json(event: Any) -> dict[str, Any]:
    name = type(event).__name__
    if isinstance(event, WidgetRequest):
        return {"type": name, **widget_json(event)}
    if name == "ComputerActions":
        return {"type": name, "agent_id": getattr(event, "agent_id", ""), "actions": []}
    if name == "AgentStateUpdate":
        return {
            "type": name,
            "agent_id": event.agent_id,
            "session_id": event.session_id,
            "is_running": event.is_running,
            "is_composing": event.is_composing,
        }
    if name == "BoxStateChanged":
        return {"type": name, "run_state": event.run_state}
    if is_dataclass(event) and not isinstance(event, type):
        data = asdict(event)
        data.pop("raw", None)
        data.pop("live_state", None)
        data["type"] = name
        return json_safe(data)
    return {"type": name}
