import pytest
from backend.local_auth import COOKIE
from starlette.websockets import WebSocketDisconnect


def test_auth_status_open(client):
    body = client.get("/api/auth/status").json()
    assert body["password_enabled"] is False
    assert body["authenticated"] is True
    assert body["needs_login"] is False


def test_settings_without_cursor(client):
    body = client.get("/api/settings").json()
    assert body["password_enabled"] is False
    assert body["cursor"]["signed_in"] is False
    assert body["login"]["state"] in {"idle", "pending", "complete", "failed"}


def test_password_protects_api_and_ws(client):
    res = client.post("/api/settings/password", json={"password": "long-enough"})
    assert res.status_code == 200
    assert client.cookies.get(COOKIE)
    assert client.get("/api/me").status_code == 200

    from backend.app import app
    from fastapi.testclient import TestClient

    with TestClient(app) as other:
        blocked = other.get("/api/me")
        assert blocked.status_code == 401
        assert other.get("/api/auth/status").json()["needs_login"] is True
        bad = other.post("/api/auth/login", json={"password": "nope-nope"})
        assert bad.status_code == 401
        ok = other.post("/api/auth/login", json={"password": "long-enough"})
        assert ok.status_code == 200
        assert other.get("/api/me").status_code == 200
        with other.websocket_connect("/ws/events") as ws:
            assert ws.receive_json()["type"] == "Hello"

    from fastapi.testclient import TestClient as TC

    with TC(app) as anon:
        with anon.websocket_connect("/ws/events") as ws:
            with pytest.raises(WebSocketDisconnect) as exc:
                ws.receive_json()
            assert exc.value.code == 4401


def test_cursor_creds_and_logout(client, stub):
    missing = client.post("/api/settings/cursor/creds", json={})
    assert missing.status_code == 400
    saved = client.post(
        "/api/settings/cursor/creds",
        json={"access_token": "aaa", "refresh_token": "bbb"},
    )
    assert saved.status_code == 200
    body = saved.json()["cursor"]
    assert body["source"] == "instance"
    assert "aaa" not in str(saved.json())
    assert stub.calls[-1][0] == "reload_client"
    out = client.post("/api/settings/cursor/logout")
    assert out.json()["cursor"]["signed_in"] is False


def test_cursor_login_start_and_cancel(client, monkeypatch):
    async def fake_start():
        return {"state": "pending", "url": "https://cursor.com/loginDeepControl?x=1", "error": None}

    monkeypatch.setattr(client.app.state.cursor_login, "start", fake_start)
    res = client.post("/api/settings/cursor/login/start")
    assert res.status_code == 200
    assert "loginDeepControl" in res.json()["url"]
    assert client.get("/api/settings/cursor/login").status_code == 200
    assert client.post("/api/settings/cursor/login/cancel").json()["ok"] is True


def test_disable_password(client):
    client.post("/api/settings/password", json={"password": "long-enough"})
    bad = client.post("/api/settings/password/disable", json={"current": "wrong-pass"})
    assert bad.status_code == 401
    ok = client.post("/api/settings/password/disable", json={"current": "long-enough"})
    assert ok.status_code == 200
    from backend.app import app
    from fastapi.testclient import TestClient

    with TestClient(app) as other:
        assert other.get("/api/me").status_code == 200
