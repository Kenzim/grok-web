import pytest
from backend.local_auth import COOKIE, LocalAuth


def test_password_round_trip_and_session(tmp_path):
    auth = LocalAuth(tmp_path / "config.json")
    assert auth.enabled() is False
    assert auth.http_allowed(_req("GET", "/api/me", cookies={})) is True
    auth.set_password("long-enough", current=None)
    assert auth.enabled() is True
    assert auth.verify_password("long-enough") is True
    assert auth.verify_password("wrong-pass") is False
    token = auth.issue_token()
    assert auth.check_cookie(token) is True
    assert auth.check_cookie("nope") is False
    assert auth.check_cookie(token[:-4] + "dead") is False
    assert auth.http_allowed(_req("GET", "/api/me", cookies={})) is False
    assert auth.http_allowed(_req("GET", "/api/auth/status", cookies={})) is True
    assert auth.http_allowed(_req("POST", "/api/auth/login", cookies={})) is True
    assert auth.http_allowed(_req("GET", "/api/health", cookies={})) is True
    assert auth.http_allowed(_req("OPTIONS", "/api/me", cookies={})) is True
    assert auth.http_allowed(_req("GET", "/", cookies={})) is True
    assert auth.http_allowed(_req("GET", "/api/me", cookies={COOKIE: token})) is True
    assert auth.ws_allowed(_ws({})) is False
    assert auth.ws_allowed(_ws({COOKIE: token})) is True


def test_set_password_requires_current_and_length(tmp_path):
    auth = LocalAuth(tmp_path / "cfg.json")
    with pytest.raises(ValueError):
        auth.set_password("short", current=None)
    auth.set_password("long-enough", current=None)
    with pytest.raises(PermissionError):
        auth.set_password("another-one", current="nope")
    auth.set_password("another-one", current="long-enough")
    assert auth.verify_password("another-one")
    with pytest.raises(PermissionError):
        auth.disable_password("wrong-pass")
    auth.disable_password("another-one")
    assert auth.enabled() is False


class _Req:
    def __init__(self, method: str, path: str, cookies: dict) -> None:
        self.method = method
        self.cookies = cookies
        self.url = type("U", (), {"path": path, "scheme": "http"})()


class _Ws:
    def __init__(self, cookies: dict) -> None:
        self.cookies = cookies


def _req(method: str, path: str, cookies: dict):
    return _Req(method, path, cookies)


def _ws(cookies: dict):
    return _Ws(cookies)
