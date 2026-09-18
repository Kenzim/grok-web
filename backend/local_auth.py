"""Optional password gate for this grok-web instance.

Disabled until a password is set in Settings. Tokens never go in cookies;
the cookie is an HMAC session bound to a secret in ``data/config.json``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Any

from fastapi import Request, WebSocket
from starlette.responses import JSONResponse, Response

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "data" / "config.json"
COOKIE = "grokweb_session"
TTL_SEC = 7 * 24 * 3600
_PBKDF2_ITERS = 210_000
PUBLIC_PATHS = {
    ("GET", "/api/health"),
    ("GET", "/api/auth/status"),
    ("POST", "/api/auth/login"),
}


def _b64(data: bytes) -> str:
    return data.hex()


class LocalAuth:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CONFIG_PATH
        self._data = self._load()

    def _load(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            raw = {}
        if not isinstance(raw, dict):
            raw = {}
        if not raw.get("session_secret"):
            raw["session_secret"] = secrets.token_hex(32)
            self._write(raw)
        return raw

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        try:
            self.path.chmod(0o600)
        except OSError:
            pass
        self._data = data

    def reload(self) -> None:
        self._data = self._load()

    def enabled(self) -> bool:
        return bool(self._data.get("password_hash"))

    def _secret(self) -> bytes:
        return str(self._data.get("session_secret") or "").encode("utf-8")

    def status(self, request: Request) -> dict[str, Any]:
        authed = (not self.enabled()) or self.check_cookie(request.cookies.get(COOKIE))
        return {
            "password_enabled": self.enabled(),
            "authenticated": authed,
            "needs_login": self.enabled() and not authed,
        }

    def http_allowed(self, request: Request) -> bool:
        if not self.enabled():
            return True
        if request.method == "OPTIONS":
            return True
        path = request.url.path
        if not path.startswith("/api") and not path.startswith("/ws"):
            return True
        if (request.method, path) in PUBLIC_PATHS:
            return True
        return self.check_cookie(request.cookies.get(COOKIE))

    def ws_allowed(self, websocket: WebSocket) -> bool:
        if not self.enabled():
            return True
        return self.check_cookie(websocket.cookies.get(COOKIE))

    def check_cookie(self, token: str | None) -> bool:
        if not token or not self._secret():
            return False
        parts = token.split(".")
        if len(parts) != 3:
            return False
        exp_s, nonce, sig = parts
        payload = f"{exp_s}.{nonce}"
        expect = hmac.new(self._secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expect, sig):
            return False
        try:
            exp = int(exp_s)
        except ValueError:
            return False
        return exp > time.time()

    def issue_token(self) -> str:
        exp = int(time.time()) + TTL_SEC
        nonce = secrets.token_urlsafe(16)
        payload = f"{exp}.{nonce}"
        sig = hmac.new(self._secret(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
        return f"{payload}.{sig}"

    def attach_cookie(self, response: Response, request: Request) -> None:
        response.set_cookie(
            COOKIE,
            self.issue_token(),
            httponly=True,
            samesite="lax",
            max_age=TTL_SEC,
            path="/",
            secure=request.url.scheme == "https",
        )

    def clear_cookie(self, response: Response) -> None:
        response.delete_cookie(COOKIE, path="/")

    @staticmethod
    def hash_password(password: str) -> str:
        salt = secrets.token_bytes(16)
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _PBKDF2_ITERS)
        return f"pbkdf2_sha256${_PBKDF2_ITERS}${_b64(salt)}${_b64(dk)}"

    def verify_password(self, password: str) -> bool:
        stored = str(self._data.get("password_hash") or "")
        if not stored:
            return False
        try:
            kind, iters_s, salt_hex, dk_hex = stored.split("$", 3)
        except ValueError:
            return False
        if kind != "pbkdf2_sha256":
            return False
        try:
            iters = int(iters_s)
            salt = bytes.fromhex(salt_hex)
            dk = bytes.fromhex(dk_hex)
        except ValueError:
            return False
        check = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iters)
        return hmac.compare_digest(check, dk)

    def set_password(self, password: str, *, current: str | None) -> None:
        if len(password) < 8:
            raise ValueError("password must be at least 8 characters")
        if self.enabled():
            if not current or not self.verify_password(current):
                raise PermissionError("current password required")
        data = dict(self._data)
        data["password_hash"] = self.hash_password(password)
        self._write(data)

    def disable_password(self, current: str) -> None:
        if not self.enabled():
            return
        if not self.verify_password(current):
            raise PermissionError("current password required")
        data = dict(self._data)
        data.pop("password_hash", None)
        self._write(data)


def deny() -> JSONResponse:
    return JSONResponse({"detail": "auth required"}, status_code=401)
