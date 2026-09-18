import asyncio
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from backend.vnc import VncStore, proxy_vnc


def _session(**kwargs):
    defaults = dict(
        run_state="RUNNING",
        connect_url=lambda: "wss://box/websockify?network_token=abc",
        websocket_headers=lambda: {"x-anyrun-network-token": "abc"},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_vnc_store_round_trip_and_unknown_token():
    store = VncStore()
    token = store.put(_session())
    row = store.take(token)
    assert row is not None
    assert row["url"].startswith("wss://")
    assert row["headers"]["x-anyrun-network-token"] == "abc"
    assert store.take("missing") is None


def test_vnc_store_expired_token():
    store = VncStore()
    token = store.put(
        _session(
            connect_url=lambda: "wss://box/websockify",
            websocket_headers=lambda: {},
        )
    )
    store._rows[token]["exp"] = 0
    assert store.take(token) is None
    assert token not in store._rows


class FakeClientWS:
    def __init__(self, incoming: list[dict]) -> None:
        self.incoming = list(incoming)
        self.sent_bytes: list[bytes] = []
        self.sent_text: list[str] = []
        self.closed: tuple[int | None, str | None] | None = None

    async def receive(self) -> dict:
        if not self.incoming:
            await asyncio.sleep(30)
            return {"type": "websocket.disconnect"}
        return self.incoming.pop(0)

    async def send_bytes(self, data: bytes) -> None:
        self.sent_bytes.append(data)

    async def send_text(self, data: str) -> None:
        self.sent_text.append(data)

    async def close(self, code: int | None = None, reason: str | None = None) -> None:
        self.closed = (code, reason)


class FakeRemote:
    def __init__(self, outgoing: list, hang: bool = True) -> None:
        self.outgoing = list(outgoing)
        self.sent: list[object] = []
        self._hang = hang
        self._closed = asyncio.Event()
        self.close_raises = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self.outgoing:
            return self.outgoing.pop(0)
        if self._hang:
            await self._closed.wait()
            raise StopAsyncIteration
        raise StopAsyncIteration

    async def send(self, data) -> None:
        self.sent.append(data)

    async def close(self) -> None:
        self._closed.set()
        if self.close_raises:
            raise RuntimeError("already closed")


@pytest.mark.asyncio
async def test_proxy_vnc_missing_websockets(monkeypatch):
    monkeypatch.setitem(sys.modules, "websockets", None)
    ws = FakeClientWS([])
    await proxy_vnc(ws, {"url": "wss://box", "headers": {}})
    assert ws.closed == (1011, "websockets missing")


@pytest.mark.asyncio
async def test_proxy_vnc_forwards_client_and_server(monkeypatch):
    remote = FakeRemote(outgoing=[b"rfb", "txt"])
    incoming = [
        {"type": "websocket.receive", "bytes": b"cli"},
        {"type": "websocket.receive", "text": "ping"},
        {"type": "websocket.receive"},
        {"type": "websocket.disconnect"},
    ]
    ws = FakeClientWS(incoming)

    async def connect(url, **kwargs):
        assert url == "wss://box"
        assert kwargs["additional_headers"]["x-token"] == "n"
        return remote

    fake_ws = SimpleNamespace(connect=connect)
    monkeypatch.setitem(sys.modules, "websockets", fake_ws)
    await proxy_vnc(ws, {"url": "wss://box", "headers": {"x-token": "n"}})
    assert b"cli" in remote.sent
    assert "ping" in remote.sent
    assert b"rfb" in ws.sent_bytes
    assert "txt" in ws.sent_text
    assert ws.closed is not None


@pytest.mark.asyncio
async def test_proxy_vnc_falls_back_to_extra_headers(monkeypatch):
    remote = FakeRemote(outgoing=[], hang=False)
    ws = FakeClientWS([{"type": "websocket.disconnect"}])

    async def connect(url, **kwargs):
        if "additional_headers" in kwargs:
            raise TypeError("old client")
        assert kwargs["extra_headers"] == {"h": "1"}
        return remote

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=connect))
    await proxy_vnc(ws, {"url": "wss://box", "headers": {"h": "1"}})
    assert ws.closed is not None


@pytest.mark.asyncio
async def test_proxy_vnc_connect_failure_closes_client(monkeypatch):
    ws = FakeClientWS([])

    async def connect(url, **kwargs):
        raise OSError("refused")

    monkeypatch.setitem(sys.modules, "websockets", SimpleNamespace(connect=connect))
    await proxy_vnc(ws, {"url": "wss://box", "headers": {}})
    assert ws.closed is not None


@pytest.mark.asyncio
async def test_proxy_vnc_swallows_remote_close_errors(monkeypatch):
    remote = FakeRemote(outgoing=[b"x"])
    remote.close_raises = True
    ws = FakeClientWS([{"type": "websocket.disconnect"}])
    monkeypatch.setitem(
        sys.modules,
        "websockets",
        SimpleNamespace(connect=AsyncMock(return_value=remote)),
    )
    await proxy_vnc(ws, {"url": "wss://box"})
    assert ws.closed is not None
