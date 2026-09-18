from __future__ import annotations

import pytest
from backend.app import app
from backend.cursor_creds import CursorLogin
from backend.local_auth import LocalAuth
from fastapi.testclient import TestClient

from tests.fakes import StubRuntime


@pytest.fixture
def stub() -> StubRuntime:
    return StubRuntime()


@pytest.fixture
def client(stub: StubRuntime, tmp_path, monkeypatch):
    config = tmp_path / "config.json"
    creds = tmp_path / "cursor-auth.json"
    monkeypatch.setattr("backend.local_auth.CONFIG_PATH", config)
    monkeypatch.setattr("backend.cursor_creds.AUTH_PATH", creds)
    monkeypatch.setattr("backend.cursor_creds.AUTH_CANDIDATES", [])
    monkeypatch.delenv("GROKBOT_TOKEN", raising=False)
    monkeypatch.setattr("backend.app.AUTH_PATH", creds)
    app.state.rt = stub
    app.state.guard = LocalAuth(config)
    app.state.cursor_login = CursorLogin(path=creds, on_saved=stub.reload_client)
    with TestClient(app) as c:
        yield c
    app.state.rt = stub
