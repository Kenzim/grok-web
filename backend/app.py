"""FastAPI BFF for the Grok Bot web client."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.responses import JSONResponse

from backend.cursor_creds import (
    AUTH_PATH,
    CursorLogin,
    clear_tokens,
    inspect,
    save_tokens,
)
from backend.local_auth import LocalAuth, deny
from backend.runtime import Runtime, http_status_for
from backend.vnc import proxy_vnc

log = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    if getattr(app.state, "guard", None) is None:
        app.state.guard = LocalAuth()

    async def _reload() -> None:
        await app.state.rt.reload_client()

    if getattr(app.state, "cursor_login", None) is None:
        app.state.cursor_login = CursorLogin(on_saved=_reload)
    elif app.state.cursor_login.on_saved is None:
        app.state.cursor_login.on_saved = _reload

    owned = getattr(app.state, "rt", None) is None
    if owned:
        rt = Runtime()
        app.state.rt = rt
        await rt.start()
    try:
        yield
    finally:
        login = getattr(app.state, "cursor_login", None)
        if login is not None:
            await login.cancel()
        if owned:
            await app.state.rt.stop()


app = FastAPI(title="grok-web", lifespan=lifespan)


@app.middleware("http")
async def instance_auth(request: Request, call_next):
    guard = getattr(request.app.state, "guard", None)
    if guard is not None and not guard.http_allowed(request):
        return deny()
    return await call_next(request)


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


def guard() -> LocalAuth:
    return app.state.guard


def cursor_login() -> CursorLogin:
    return app.state.cursor_login


async def call(fn, *args, **kwargs):
    try:
        return await fn(*args, **kwargs)
    except HTTPException:
        raise
    except Exception as exc:
        log.exception("%s", exc)
        raise HTTPException(http_status_for(exc), str(exc)) from exc


async def _accept_ws(websocket: WebSocket) -> bool:
    await websocket.accept()
    g = getattr(app.state, "guard", None)
    if g is not None and not g.ws_allowed(websocket):
        await websocket.close(code=4401, reason="auth required")
        return False
    return True


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


class PasswordBody(BaseModel):
    password: str = ""
    current: str | None = None


class CursorCredsBody(BaseModel):
    access_token: str = ""
    refresh_token: str = ""
    api_key: str = ""


@app.get("/api/health")
async def health() -> dict[str, Any]:
    runtime = rt()
    last_seen = 0.0
    if runtime.watcher is not None:
        last_seen = float(getattr(runtime.watcher, "last_seen", 0.0) or 0.0)
    return {"ok": runtime.last_error is None, "error": runtime.last_error, "last_seen": last_seen}


@app.get("/api/auth/status")
async def auth_status(request: Request) -> dict[str, Any]:
    return guard().status(request)


@app.post("/api/auth/login")
async def auth_login(request: Request, body: PasswordBody):
    if not guard().enabled():
        raise HTTPException(400, "password protection is not enabled")
    if not guard().verify_password(body.password):
        raise HTTPException(401, "invalid password")
    resp = JSONResponse({"ok": True})
    guard().attach_cookie(resp, request)
    return resp


@app.post("/api/auth/logout")
async def auth_logout():
    resp = JSONResponse({"ok": True})
    guard().clear_cookie(resp)
    return resp


@app.get("/api/settings")
async def settings() -> dict[str, Any]:
    account = None
    try:
        account = await rt().me()
    except Exception:
        account = None
    return {
        "password_enabled": guard().enabled(),
        "cursor": {**inspect(AUTH_PATH), "account": account},
        "login": cursor_login().public(),
    }


@app.post("/api/settings/password")
async def settings_password(request: Request, body: PasswordBody):
    try:
        guard().set_password(body.password, current=body.current)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(401, str(exc)) from exc
    resp = JSONResponse({"ok": True, "password_enabled": True})
    guard().attach_cookie(resp, request)
    return resp


@app.post("/api/settings/password/disable")
async def settings_password_disable(body: PasswordBody):
    try:
        guard().disable_password(body.current or body.password)
    except PermissionError as exc:
        raise HTTPException(401, str(exc)) from exc
    resp = JSONResponse({"ok": True, "password_enabled": False})
    guard().clear_cookie(resp)
    return resp


@app.post("/api/settings/cursor/login/start")
async def cursor_login_start() -> dict[str, Any]:
    return await call(cursor_login().start)


@app.get("/api/settings/cursor/login")
async def cursor_login_status() -> dict[str, Any]:
    return cursor_login().public()


@app.post("/api/settings/cursor/login/cancel")
async def cursor_login_cancel() -> dict[str, Any]:
    await cursor_login().cancel()
    return {"ok": True, **cursor_login().public()}


@app.post("/api/settings/cursor/creds")
async def cursor_creds_save(body: CursorCredsBody) -> dict[str, Any]:
    key = body.api_key.strip()
    access = body.access_token.strip()
    if not key and not access:
        raise HTTPException(400, "access_token or api_key required")
    save_tokens(
        AUTH_PATH,
        access_token=access or None,
        refresh_token=body.refresh_token.strip() or None,
        api_key=key or None,
    )
    await call(rt().reload_client)
    return {"ok": True, "cursor": inspect(AUTH_PATH)}


@app.post("/api/settings/cursor/logout")
async def cursor_logout() -> dict[str, Any]:
    await cursor_login().cancel()
    clear_tokens(AUTH_PATH)
    await call(rt().reload_client)
    return {"ok": True, "cursor": inspect(AUTH_PATH)}


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
    if not await _accept_ws(websocket):
        return
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
    if not await _accept_ws(websocket):
        return
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
