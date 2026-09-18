from __future__ import annotations

import pytest
from backend.app import app
from fastapi.testclient import TestClient

from tests.fakes import StubRuntime


@pytest.fixture
def stub() -> StubRuntime:
    return StubRuntime()


@pytest.fixture
def client(stub: StubRuntime):
    app.state.rt = stub
    with TestClient(app) as c:
        yield c
    app.state.rt = stub
