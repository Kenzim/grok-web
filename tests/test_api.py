import pytest
from grokbot.errors import AuthError, GrokBotError, NotFoundError, RefusalError, UnauthorizedError
from starlette.websockets import WebSocketDisconnect

from tests.fakes import StubRuntime


def test_health(client, stub: StubRuntime):
    res = client.get("/api/health")
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["last_seen"] == 0.0
    stub.watcher = type("W", (), {"last_seen": 9.5})()
    assert client.get("/api/health").json()["last_seen"] == 9.5


def test_me_and_agents(client, stub: StubRuntime):
    me = client.get("/api/me")
    assert me.status_code == 200
    assert me.json()["email"] == "a@b.c"
    agents = client.get("/api/agents")
    assert agents.status_code == 200
    assert agents.json()[0]["agent_id"] == "agent-1"


def test_history_clamps_limit(client, stub: StubRuntime):
    res = client.get("/api/agents/agent-1/history?limit=9999")
    assert res.status_code == 200
    assert stub.calls[-1] == ("history", ("agent-1", 200))
    res = client.get("/api/agents/agent-1/history?limit=0")
    assert stub.calls[-1] == ("history", ("agent-1", 1))


def test_send_requires_text(client, stub: StubRuntime):
    res = client.post("/api/agents/agent-1/send", json={"text": "   "})
    assert res.status_code == 400
    assert not any(c[0] == "send" for c in stub.calls)
    res = client.post("/api/agents/agent-1/send", json={"text": "hello"})
    assert res.status_code == 200
    assert stub.calls[-1] == ("send", ("agent-1", "hello"))


def test_interrupt(client):
    res = client.post("/api/agents/agent-1/interrupt")
    assert res.status_code == 200
    assert res.json() == {"ok": True}


def test_widgets(client, stub: StubRuntime):
    payload = {
        "agent_id": "agent-1",
        "session_id": "",
        "entry_id": "w1",
        "kind": "approval",
        "value": "yes",
        "values": {"k": "v"},
        "approved": True,
    }
    assert client.post("/api/widgets/respond", json=payload).json() == {"ok": True}
    assert client.post("/api/widgets/dismiss", json=payload).json() == {"ok": True}
    assert client.post("/api/widgets/submit-form", json=payload).json() == {"ok": True}
    assert client.post("/api/widgets/submit-secret", json=payload).json() == {"ok": True}
    missing = {**payload, "approved": None}
    assert client.post("/api/widgets/resolve-approval", json=missing).status_code == 400
    assert client.post("/api/widgets/resolve-approval", json=payload).json() == {"ok": True}
    names = [c[0] for c in stub.calls]
    assert names.count("widget_respond") == 1
    assert names.count("widget_resolve_approval") == 1


def test_desktop(client, stub: StubRuntime):
    res = client.post("/api/desktop", json={"wake": False})
    assert res.status_code == 200
    assert res.json()["run_state"] == "RUNNING"
    assert stub.calls[-1] == ("ensure_desktop", False)


def test_error_mapping(client, stub: StubRuntime):
    stub.fail = UnauthorizedError("nope")
    assert client.get("/api/me").status_code == 401
    stub.fail = AuthError("expired")
    assert client.get("/api/me").status_code == 401
    stub.fail = NotFoundError("gone")
    assert client.get("/api/agents/missing/history").status_code == 404
    stub.fail = RefusalError("refused")
    assert client.post("/api/agents/agent-1/send", json={"text": "x"}).status_code == 409
    stub.fail = GrokBotError("upstream")
    assert client.get("/api/agents").status_code == 502
    stub.fail = RuntimeError("boom")
    assert client.get("/api/me").status_code == 500
    stub.fail = None


def test_health_reports_runtime_error(client, stub: StubRuntime):
    stub.last_error = "watch broke"
    body = client.get("/api/health").json()
    assert body["ok"] is False
    assert body["error"] == "watch broke"


def test_desktop_wake_flag(client, stub: StubRuntime):
    res = client.post("/api/desktop", json={"wake": True})
    assert res.status_code == 200
    assert stub.calls[-1] == ("ensure_desktop", True)


def test_events_websocket_client_close(client):
    with client.websocket_connect("/ws/events") as ws:
        assert ws.receive_json()["type"] == "Hello"
        ws.close()


def test_vnc_websocket_valid_token(client, stub: StubRuntime, monkeypatch):
    from types import SimpleNamespace

    async def fake_proxy(websocket, target):
        await websocket.send_text(target["url"])
        await websocket.close()

    monkeypatch.setattr("backend.app.proxy_vnc", fake_proxy)
    token = stub.vnc.put(
        SimpleNamespace(
            run_state="RUNNING",
            connect_url=lambda: "wss://box/websockify",
            websocket_headers=lambda: {},
        )
    )
    with client.websocket_connect(f"/ws/vnc?token={token}") as ws:
        assert ws.receive_text() == "wss://box/websockify"


def test_lifespan_starts_runtime_when_missing(monkeypatch):
    from backend.app import app
    from fastapi.testclient import TestClient

    class FakeRT:
        def __init__(self) -> None:
            self.ops: list[str] = []
            self.last_error = None
            self.watcher = None
            self.hub = stub_hub()
            self.vnc = None

        async def start(self) -> None:
            self.ops.append("start")

        async def stop(self) -> None:
            self.ops.append("stop")

    def stub_hub():
        from backend.runtime import Hub

        return Hub()

    fake = FakeRT()
    monkeypatch.setattr("backend.app.Runtime", lambda: fake)
    app.state.rt = None
    with TestClient(app):
        assert fake.ops == ["start"]
    assert fake.ops == ["start", "stop"]


def test_events_websocket_hello(client):
    with client.websocket_connect("/ws/events") as ws:
        assert ws.receive_json()["type"] == "Hello"


def test_vnc_websocket_requires_token(client):
    with client.websocket_connect("/ws/vnc") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
        assert exc.value.code == 1008


def test_vnc_websocket_rejects_bad_token(client):
    with client.websocket_connect("/ws/vnc?token=nope") as ws:
        with pytest.raises(WebSocketDisconnect) as exc:
            ws.receive_text()
        assert exc.value.code == 1008
