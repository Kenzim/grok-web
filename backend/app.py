"""FastAPI BFF for the Grok Bot web client."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.runtime import Runtime, http_status_for
from backend.vnc import proxy_vnc

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    owned = getattr(app.state, "rt", None) is None
    if owned:
        rt = Runtime()
        app.state.rt = rt
        await rt.start()
    try:
        yield
    finally:
        if owned:
            await app.state.rt.stop()


app = FastAPI(title="grok-web", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5180",
        "http://localhost:5180",
        "http://127.0.0.1:5173",
        "http://localhost:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def rt() -> Runtime:
    return app.state.rt


async def call(fn, *args, **kwargs):
    try:
        return await fn(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("%s", exc)
        raise HTTPException(http_status_for(exc), str(exc)) from exc


class SendBody(BaseModel):
    text: str


class DesktopBody(BaseModel):
    wake: bool = False


class WidgetBody(BaseModel):
    agent_id: str
    session_id: str = ""
    entry_id: str
    kind: str = ""
    prompt: str = ""
    request_id: str = ""
    value: str = ""
    values: dict[str, str] | None = None
    approved: bool | None = None


@app.get("/api/health")
async def health() -> dict[str, Any]:
    runtime = rt()
    last_seen = 0.0
    if runtime.watcher is not None:
        last_seen = float(getattr(runtime.watcher, "last_seen", 0.0) or 0.0)
    return {"ok": runtime.last_error is None, "error": runtime.last_error, "last_seen": last_seen}


@app.get("/api/me")
async def me() -> dict[str, Any]:
    return await call(rt().me)


@app.get("/api/agents")
async def agents() -> list[dict[str, Any]]:
    return await call(rt().list_agents)


@app.get("/api/agents/{agent_id}/history")
async def history(agent_id: str, limit: int = 100) -> dict[str, Any]:
    return await call(rt().history, agent_id, max(1, min(limit, 200)))


@app.post("/api/agents/{agent_id}/send")
async def send(agent_id: str, body: SendBody) -> dict[str, Any]:
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "text required")
    return await call(rt().send, agent_id, text)


@app.post("/api/agents/{agent_id}/interrupt")
async def interrupt(agent_id: str) -> dict[str, Any]:
    return await call(rt().interrupt, agent_id)


@app.post("/api/widgets/respond")
async def widget_respond(body: WidgetBody) -> dict[str, Any]:
    await call(rt().widget_respond, body.model_dump())
    return {"ok": True}


@app.post("/api/widgets/dismiss")
async def widget_dismiss(body: WidgetBody) -> dict[str, Any]:
    await call(rt().widget_dismiss, body.model_dump())
    return {"ok": True}


@app.post("/api/widgets/submit-form")
async def widget_submit_form(body: WidgetBody) -> dict[str, Any]:
    await call(rt().widget_submit_form, body.model_dump())
    return {"ok": True}


@app.post("/api/widgets/submit-secret")
async def widget_submit_secret(body: WidgetBody) -> dict[str, Any]:
    await call(rt().widget_submit_secret, body.model_dump())
    return {"ok": True}


@app.post("/api/widgets/resolve-approval")
async def widget_resolve_approval(body: WidgetBody) -> dict[str, Any]:
    if body.approved is None:
        raise HTTPException(400, "approved required")
    await call(rt().widget_resolve_approval, body.model_dump())
    return {"ok": True}


@app.post("/api/desktop")
async def desktop(body: DesktopBody) -> dict[str, Any]:
    return await call(rt().ensure_desktop, wake=body.wake)


@app.websocket("/ws/events")
async def events_ws(websocket: WebSocket) -> None:
    await websocket.accept()
    runtime = rt()
    await runtime.hub.add(websocket)
    try:
        await websocket.send_json({"type": "Hello"})
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await runtime.hub.discard(websocket)


@app.websocket("/ws/vnc")
async def vnc_ws(websocket: WebSocket, token: str | None = None) -> None:
    await websocket.accept()
    if not token:
        await websocket.close(code=1008, reason="token required")
        return
    target = rt().vnc.take(token)
    if target is None:
        await websocket.close(code=1008, reason="invalid token")
        return
    await proxy_vnc(websocket, target)


_DIST = ROOT / "frontend" / "dist"
if _DIST.is_dir():
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="spa")
