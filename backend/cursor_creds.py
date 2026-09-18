"""Instance Cursor credentials and PKCE browser login.

The SPA never sees access or refresh tokens. Sign-in opens Cursor's
``loginDeepControl`` page; this process polls ``/auth/poll`` and writes
``data/cursor-auth.json``. HostFiles / ``GROKBOT_TOKEN`` remain fallbacks.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import secrets
import time
import uuid
from pathlib import Path
from typing import Any, Awaitable, Callable

import grokbot
import httpx
from grokbot.auth import AUTH_CANDIDATES, jwt_exp, jwt_payload
from grokbot.errors import AuthError

log = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent
AUTH_PATH = ROOT / "data" / "cursor-auth.json"
LOGIN_PAGE = "https://cursor.com/loginDeepControl"
POLL_URL = "https://api2.cursor.sh/auth/poll"
POLL_TIMEOUT_SEC = 300.0
POLL_INTERVAL_SEC = 2.0

OnSaved = Callable[[], Awaitable[None]]


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode("utf-8")).digest())
    return verifier, challenge


def login_url(challenge: str, login_id: str) -> str:
    return (
        f"{LOGIN_PAGE}?challenge={challenge}&uuid={login_id}"
        f"&mode=login&redirectTarget=cli"
    )


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def save_tokens(
    path: Path,
    *,
    access_token: str | None = None,
    refresh_token: str | None = None,
    api_key: str | None = None,
) -> None:
    data: dict[str, Any] = {}
    if api_key:
        data["apiKey"] = api_key.strip()
    if access_token:
        data["accessToken"] = access_token.strip()
    if refresh_token:
        data["refreshToken"] = refresh_token.strip()
    if not data:
        raise ValueError("no credentials to save")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    tmp.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def clear_tokens(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return


def _meta_from_mapping(data: dict[str, Any], source: str) -> dict[str, Any]:
    token = data.get("accessToken") or data.get("access_token")
    refresh = data.get("refreshToken") or data.get("refresh_token")
    api_key = data.get("apiKey") or data.get("api_key")
    access = token.strip() if isinstance(token, str) else ""
    exp = jwt_exp(access) if access else None
    expired = bool(exp is not None and exp <= time.time())
    email = ""
    if access:
        payload = jwt_payload(access)
        sub = payload.get("email") or payload.get("sub") or ""
        email = str(sub) if sub else ""
    signed_in = bool(access and not expired)
    if isinstance(api_key, str) and api_key.strip():
        signed_in = True
    return {
        "signed_in": signed_in,
        "source": source,
        "has_refresh": bool(isinstance(refresh, str) and refresh.strip()),
        "has_api_key": bool(isinstance(api_key, str) and api_key.strip()),
        "expires_at": exp,
        "expired": expired,
        "subject": email,
    }


def inspect(path: Path | None = None) -> dict[str, Any]:
    target = path or AUTH_PATH
    data = _read_json(target)
    if data:
        return _meta_from_mapping(data, "instance")
    for host in AUTH_CANDIDATES:
        data = _read_json(host)
        if data and (data.get("accessToken") or data.get("access_token") or data.get("authInfo")):
            info = data.get("authInfo") if isinstance(data.get("authInfo"), dict) else data
            if isinstance(info, dict):
                return _meta_from_mapping(info, "host")
    env = (os.environ.get("GROKBOT_TOKEN") or "").strip()
    if env:
        return _meta_from_mapping({"accessToken": env}, "env")
    return {
        "signed_in": False,
        "source": None,
        "has_refresh": False,
        "has_api_key": False,
        "expires_at": None,
        "expired": False,
        "subject": "",
    }


def build_auth(path: Path | None = None) -> grokbot.auth.AuthStrategy:
    target = path or AUTH_PATH
    data = _read_json(target)
    if data:
        key = data.get("apiKey") or data.get("api_key")
        if isinstance(key, str) and key.strip():
            return grokbot.auth.ApiKey(key.strip())
        return grokbot.auth.HostFiles(paths=[target])
    return grokbot.auth.auto()


class CursorLogin:
    def __init__(self, path: Path | None = None, on_saved: OnSaved | None = None) -> None:
        self.path = path or AUTH_PATH
        self.on_saved = on_saved
        self.state = "idle"
        self.url: str | None = None
        self.error: str | None = None
        self._uuid: str | None = None
        self._verifier: str | None = None
        self._task: asyncio.Task[None] | None = None
        self._poller: Callable[..., Awaitable[dict[str, Any] | None]] | None = None

    def public(self) -> dict[str, Any]:
        return {"state": self.state, "url": self.url, "error": self.error}

    async def start(self) -> dict[str, Any]:
        await self.cancel()
        verifier, challenge = pkce_pair()
        login_id = str(uuid.uuid4()).lower()
        self._uuid = login_id
        self._verifier = verifier
        self.url = login_url(challenge, login_id)
        self.state = "pending"
        self.error = None
        self._task = asyncio.create_task(self._poll_loop(), name="cursor-login-poll")
        return self.public()

    async def cancel(self) -> None:
        task = self._task
        self._task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        if self.state == "pending":
            self.state = "idle"
            self.url = None
            self.error = None
        self._uuid = None
        self._verifier = None

    async def _poll_loop(self) -> None:
        deadline = time.monotonic() + POLL_TIMEOUT_SEC
        try:
            while time.monotonic() < deadline:
                tokens = await self._poll_once()
                if tokens:
                    save_tokens(
                        self.path,
                        access_token=tokens.get("accessToken"),
                        refresh_token=tokens.get("refreshToken"),
                    )
                    self.state = "complete"
                    self.error = None
                    if self.on_saved is not None:
                        await self.on_saved()
                    return
                await asyncio.sleep(POLL_INTERVAL_SEC)
            self.state = "failed"
            self.error = "Timed out waiting for Cursor sign-in"
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.exception("cursor login poll failed")
            self.state = "failed"
            self.error = str(exc)

    async def _poll_once(self) -> dict[str, Any] | None:
        if self._poller is not None:
            return await self._poller(self._uuid or "", self._verifier or "")
        if not self._uuid or not self._verifier:
            return None
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(
                POLL_URL,
                params={"uuid": self._uuid, "verifier": self._verifier},
            )
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            raise AuthError(f"Cursor poll failed HTTP {resp.status_code}")
        data = resp.json()
        if not isinstance(data, dict):
            raise AuthError("Cursor poll returned non-object")
        token = data.get("accessToken") or data.get("access_token")
        if not isinstance(token, str) or not token.strip():
            raise AuthError("Cursor poll returned no access token")
        return {
            "accessToken": token.strip(),
            "refreshToken": str(data.get("refreshToken") or data.get("refresh_token") or ""),
        }
