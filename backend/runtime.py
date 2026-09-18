"""Process-wide GrokBotClient, transcript watcher, and websocket fan-out."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import grokbot
from fastapi import WebSocket
from grokbot.errors import AuthError, GrokBotError, NotFoundError, RefusalError, UnauthorizedError
from grokbot.events import WidgetRequest

from backend.cursor_creds import build_auth
from backend.cursors import load_cursors, save_cursors
from backend.serialize import (
    account_json,
    agent_json,
    entry_json,
    event_json,
    receipt_json,
)
from backend.vnc import VncStore

log = logging.getLogger(__name__)

_CURSOR_SAVE_SEC = 1.0


class Hub:
    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def add(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.add(ws)

    async def discard(self, ws: WebSocket) -> None:
        async with self._lock:
            self._clients.discard(ws)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        async with self._lock:
            clients = list(self._clients)
        dead: list[WebSocket] = []
        for ws in clients:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            await self.discard(ws)


class Runtime:
    def __init__(self) -> None:
        self.client: grokbot.GrokBotClient | None = None
        self.watcher: Any = None
        self.hub = Hub()
        self.vnc = VncStore()
        self.last_error: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop = asyncio.Event()
        self._cursor_dirty = False
        self._last_cursor_save = 0.0

    async def start(self) -> None:
        self._stop.clear()
        try:
            self.client = grokbot.GrokBotClient(auth=build_auth())
            self.last_error = None
        except Exception as exc:
            self.client = None
            self.last_error = str(exc)
            log.exception("cursor client failed to start")
            return
        self._task = asyncio.create_task(self._watch_loop(), name="grok-web-watch")

    async def reload_client(self) -> None:
        await self.stop()
        await self.start()

    async def stop(self) -> None:
        self._stop.set()
        watcher = self.watcher
        self.watcher = None
        if watcher is not None:
            try:
                save_cursors(watcher.cursors)
            except Exception:
                log.exception("failed to persist cursors on shutdown")
            await watcher.stop()
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if self.client is not None:
            await self.client.close()
            self.client = None

    def require(self) -> grokbot.GrokBotClient:
        if self.client is None:
            raise AuthError(self.last_error or "Cursor is not signed in")
        return self.client

    async def _watch_loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._run_watch()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("watch loop failed")
            if self._stop.is_set():
                return
            await asyncio.sleep(2.0)

    async def _run_watch(self) -> None:
        client = self.require()
        watcher = client.watch()
        watcher.start(load_cursors())
        self.watcher = watcher
        self.last_error = None
        try:
            async for event in watcher:
                self._cursor_dirty = True
                self._maybe_save_cursors()
                await self.hub.broadcast(event_json(event))
        finally:
            if self._cursor_dirty and watcher.cursors:
                save_cursors(watcher.cursors)
                self._cursor_dirty = False

    def _maybe_save_cursors(self) -> None:
        watcher = self.watcher
        if not self._cursor_dirty or watcher is None:
            return
        now = time.monotonic()
        if now - self._last_cursor_save < _CURSOR_SAVE_SEC:
            return
        try:
            save_cursors(watcher.cursors)
            self._cursor_dirty = False
            self._last_cursor_save = now
        except Exception:
            log.exception("failed to persist cursors")

    async def me(self) -> dict[str, Any]:
        account = await self.require().get_me()
        return account_json(account)

    async def list_agents(self) -> list[dict[str, Any]]:
        agents = await self.require().agents.list()
        return [agent_json(a) for a in agents]

    async def history(self, agent_id: str, limit: int = 100) -> dict[str, Any]:
        chat = self.require().chat(agent_id)
        page = await chat.history(limit=limit)
        session_id = chat.session_id or ""
        return {
            "generation": page.generation,
            "session_id": session_id,
            "entries": [entry_json(agent_id, session_id, e) for e in page.entries],
        }

    async def send(self, agent_id: str, text: str) -> dict[str, Any]:
        receipt = await self.require().chat(agent_id).send(text)
        return receipt_json(receipt)

    async def interrupt(self, agent_id: str) -> dict[str, Any]:
        ok = await self.require().chat(agent_id).interrupt()
        return {"ok": ok}

    def _widget(self, body: dict[str, Any]) -> WidgetRequest:
        return WidgetRequest(
            agent_id=str(body["agent_id"]),
            session_id=str(body.get("session_id") or ""),
            entry_id=str(body["entry_id"]),
            kind=str(body.get("kind") or ""),
            prompt=str(body.get("prompt") or ""),
            request_id=str(body.get("request_id") or ""),
        )

    async def widget_respond(self, body: dict[str, Any]) -> None:
        await self.require().widgets.respond(self._widget(body), str(body.get("value") or ""))

    async def widget_dismiss(self, body: dict[str, Any]) -> None:
        await self.require().widgets.dismiss(self._widget(body))

    async def widget_submit_form(self, body: dict[str, Any]) -> None:
        values = body.get("values") if isinstance(body.get("values"), dict) else {}
        clean = {str(k): str(v) for k, v in values.items()}
        await self.require().widgets.submit_form(self._widget(body), clean)

    async def widget_submit_secret(self, body: dict[str, Any]) -> None:
        await self.require().widgets.submit_secret(self._widget(body), str(body.get("value") or ""))

    async def widget_resolve_approval(self, body: dict[str, Any]) -> None:
        approved = bool(body.get("approved"))
        await self.require().widgets.resolve_approval(self._widget(body), approved)

    async def ensure_desktop(self, *, wake: bool) -> dict[str, Any]:
        session = await self.require().desktop(wake=wake)
        token = ""
        if session.connect_url():
            token = self.vnc.put(session)
        return {
            "token": token,
            "run_state": session.run_state,
            "has_vnc": bool(token),
        }


def http_status_for(exc: Exception) -> int:
    if isinstance(exc, UnauthorizedError):
        return 401
    if isinstance(exc, AuthError):
        return 401
    if isinstance(exc, NotFoundError):
        return 404
    if isinstance(exc, RefusalError):
        return 409
    if isinstance(exc, GrokBotError):
        return 502
    return 500
