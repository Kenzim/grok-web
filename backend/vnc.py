"""Opaque VNC session tokens plus a websockify proxy.

The browser cannot attach `x-anyrun-network-token` on WebSocket; this module
holds the real connect URL and headers and proxies RFB bytes.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
from typing import Any

from fastapi import WebSocket
from grokbot.desktop import DesktopSession

log = logging.getLogger(__name__)

_TTL_SEC = 3600.0


class VncStore:
    def __init__(self) -> None:
        self._rows: dict[str, dict[str, Any]] = {}

    def put(self, session: DesktopSession) -> str:
        token = secrets.token_urlsafe(24)
        self._rows[token] = {
            "url": session.connect_url(),
            "headers": session.websocket_headers(),
            "exp": time.time() + _TTL_SEC,
            "run_state": session.run_state,
        }
        return token

    def take(self, token: str) -> dict[str, Any] | None:
        row = self._rows.get(token)
        if row is None:
            return None
        if float(row.get("exp") or 0) < time.time():
            self._rows.pop(token, None)
            return None
        return row


async def proxy_vnc(websocket: WebSocket, target: dict[str, Any]) -> None:
    url = str(target["url"])
    headers = dict(target.get("headers") or {})
    try:
        import websockets
    except ImportError:
        await websocket.close(code=1011, reason="websockets missing")
        return
    remote = None
    try:
        kwargs: dict[str, Any] = {"max_size": 8 * 1024 * 1024}
        try:
            remote = await websockets.connect(url, additional_headers=headers, **kwargs)
        except TypeError:
            remote = await websockets.connect(url, extra_headers=headers, **kwargs)

        async def up() -> None:
            while True:
                msg = await websocket.receive()
                if msg.get("type") == "websocket.disconnect":
                    break
                data = msg.get("bytes") or msg.get("text")
                if data is None:
                    continue
                if isinstance(data, str):
                    await remote.send(data)
                else:
                    await remote.send(data)

        async def down() -> None:
            async for data in remote:
                if isinstance(data, (bytes, bytearray)):
                    await websocket.send_bytes(bytes(data))
                else:
                    await websocket.send_text(str(data))

        await asyncio.wait(
            [asyncio.create_task(up()), asyncio.create_task(down())],
            return_when=asyncio.FIRST_COMPLETED,
        )
    except Exception as exc:
        log.debug("vnc proxy: %s", exc)
    finally:
        if remote is not None:
            try:
                await remote.close()
            except Exception:
                pass
        try:
            await websocket.close()
        except Exception:
            pass
