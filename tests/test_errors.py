from backend.runtime import http_status_for
from grokbot.errors import (
    AuthError,
    GrokBotError,
    NotFoundError,
    RefusalError,
    UnauthorizedError,
)


def test_http_status_mapping():
    assert http_status_for(UnauthorizedError("x")) == 401
    assert http_status_for(AuthError("x")) == 401
    assert http_status_for(NotFoundError("x")) == 404
    assert http_status_for(RefusalError("x")) == 409
    assert http_status_for(GrokBotError("x")) == 502
    assert http_status_for(RuntimeError("x")) == 500
