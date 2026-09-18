from __future__ import annotations

from typing import Any

from backend.runtime import Hub
from backend.vnc import VncStore


class StubRuntime:
    def __init__(self) -> None:
        self.hub = Hub()
        self.vnc = VncStore()
        self.last_error: str | None = None
        self.watcher = None
        self.calls: list[tuple[str, Any]] = []
        self.fail: Exception | None = None
        self.me_result = {
            "user_id": 1,
            "email": "a@b.c",
            "first_name": "A",
            "auth_id": "auth",
        }
        self.agents_result = [
            {
                "id": "1",
                "agent_id": "agent-1",
                "name": "job finder",
                "description": "",
                "harness": "box",
                "kind": "DEFAULT",
                "created_at_ms": 1,
                "title": "",
                "viewer_session_id": "",
            }
        ]
        self.history_result = {"generation": 1, "session_id": "", "entries": []}
        self.send_result = {
            "message_id": "m1",
            "dispatched": True,
            "delivery": "ACCEPTED_BOX",
            "workflow_id": None,
        }
        self.desktop_result = {"token": "tok", "run_state": "RUNNING", "has_vnc": True}

    async def reload_client(self) -> None:
        self.calls.append(("reload_client", None))

    async def _maybe_fail(self) -> None:
        if self.fail is not None:
            raise self.fail

    async def me(self) -> dict[str, Any]:
        await self._maybe_fail()
        self.calls.append(("me", None))
        return self.me_result

    async def list_agents(self) -> list[dict[str, Any]]:
        await self._maybe_fail()
        self.calls.append(("list_agents", None))
        return self.agents_result

    async def history(self, agent_id: str, limit: int = 100) -> dict[str, Any]:
        await self._maybe_fail()
        self.calls.append(("history", (agent_id, limit)))
        return self.history_result

    async def send(self, agent_id: str, text: str) -> dict[str, Any]:
        await self._maybe_fail()
        self.calls.append(("send", (agent_id, text)))
        return self.send_result

    async def interrupt(self, agent_id: str) -> dict[str, Any]:
        await self._maybe_fail()
        self.calls.append(("interrupt", agent_id))
        return {"ok": True}

    async def widget_respond(self, body: dict[str, Any]) -> None:
        await self._maybe_fail()
        self.calls.append(("widget_respond", body))

    async def widget_dismiss(self, body: dict[str, Any]) -> None:
        await self._maybe_fail()
        self.calls.append(("widget_dismiss", body))

    async def widget_submit_form(self, body: dict[str, Any]) -> None:
        await self._maybe_fail()
        self.calls.append(("widget_submit_form", body))

    async def widget_submit_secret(self, body: dict[str, Any]) -> None:
        await self._maybe_fail()
        self.calls.append(("widget_submit_secret", body))

    async def widget_resolve_approval(self, body: dict[str, Any]) -> None:
        await self._maybe_fail()
        self.calls.append(("widget_resolve_approval", body))

    async def ensure_desktop(self, *, wake: bool) -> dict[str, Any]:
        await self._maybe_fail()
        self.calls.append(("ensure_desktop", wake))
        return self.desktop_result
