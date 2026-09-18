import asyncio
from pathlib import Path

import pytest
from backend.cursor_creds import (
    CursorLogin,
    build_auth,
    clear_tokens,
    inspect,
    login_url,
    pkce_pair,
    save_tokens,
)
from grokbot.auth import ApiKey, HostFiles
from grokbot.errors import AuthError


@pytest.fixture(autouse=True)
def no_host_creds(monkeypatch):
    monkeypatch.setattr("backend.cursor_creds.AUTH_CANDIDATES", [])
    monkeypatch.delenv("GROKBOT_TOKEN", raising=False)
    monkeypatch.setattr("backend.cursor_creds.POLL_INTERVAL_SEC", 0.01)


def test_pkce_and_login_url():
    verifier, challenge = pkce_pair()
    assert verifier
    assert challenge
    assert verifier != challenge
    url = login_url(challenge, "abc-uuid")
    assert "loginDeepControl" in url
    assert "challenge=" in url
    assert "uuid=abc-uuid" in url
    assert "redirectTarget=cli" in url


def test_save_inspect_clear(tmp_path: Path):
    path = tmp_path / "cursor-auth.json"
    assert inspect(path)["signed_in"] is False
    save_tokens(path, access_token="tok", refresh_token="ref")
    meta = inspect(path)
    assert meta["source"] == "instance"
    assert meta["has_refresh"] is True
    assert "tok" not in str(meta)
    save_tokens(path, api_key="cur_key")
    assert inspect(path)["has_api_key"] is True
    assert isinstance(build_auth(path), ApiKey)
    save_tokens(path, access_token="tok")
    assert isinstance(build_auth(path), HostFiles)
    clear_tokens(path)
    assert path.exists() is False


@pytest.mark.asyncio
async def test_login_poll_saves_tokens(tmp_path: Path):
    path = tmp_path / "cursor-auth.json"
    saved: list[bool] = []

    async def on_saved():
        saved.append(True)

    login = CursorLogin(path=path, on_saved=on_saved)

    async def fake_poll(uid: str, verifier: str):
        assert uid and verifier
        return {"accessToken": "access", "refreshToken": "refresh"}

    login._poller = fake_poll
    public = await login.start()
    assert public["state"] == "pending"
    assert public["url"]
    await asyncio.sleep(0.05)
    assert login.state == "complete"
    assert saved == [True]
    assert inspect(path)["source"] == "instance"
    await login.cancel()


@pytest.mark.asyncio
async def test_login_poll_http_error(tmp_path: Path):
    login = CursorLogin(path=tmp_path / "c.json")

    async def boom(uid: str, verifier: str):
        raise AuthError("poll failed")

    login._poller = boom
    await login.start()
    await asyncio.sleep(0.05)
    assert login.state == "failed"
    assert login.error
    await login.cancel()
