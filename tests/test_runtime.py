import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.runtime import Hub, Runtime
from grokbot.errors import AuthError
from grokbot.models import Agent, SendReceipt, TranscriptEntry, TranscriptPage


class FakeWS:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.sent: list[dict] = []

    async def send_json(self, payload: dict) -> None:
        if self.fail:
            raise RuntimeError("gone")
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_hub_broadcast_drops_dead_clients():
    hub = Hub()
    live = FakeWS()
    dead = FakeWS(fail=True)
    await hub.add(live)  # type: ignore[arg-type]
    await hub.add(dead)  # type: ignore[arg-type]
    await hub.broadcast({"type": "Hello"})
    assert live.sent == [{"type": "Hello"}]
    assert dead not in hub._clients
    assert live in hub._clients


@pytest.mark.asyncio
async def test_runtime_require_and_passthrough():
    rt = Runtime()
    with pytest.raises(AuthError, match="not signed in"):
        rt.require()

    client = MagicMock()
    agent = Agent(
        id="1",
        agent_id="a1",
        name="bot",
        description="",
        harness="box",
        kind="DEFAULT",
        created_at_ms=1,
    )
    client.agents.list = AsyncMock(return_value=[agent])
    chat = MagicMock()
    chat.session_id = ""
    chat.history = AsyncMock(
        return_value=TranscriptPage(
            entries=[
                TranscriptEntry(
                    seq=1,
                    entry_kind="message",
                    entry_id="e1",
                    body={"role": "user", "content": "hi"},
                    body_raw=None,
                    blob_hash=None,
                    body_omitted=False,
                    updated_seq=1,
                )
            ],
            generation=2,
        )
    )
    chat.send = AsyncMock(
        return_value=SendReceipt(message_id="m1", dispatched=True, delivery="ACCEPTED_BOX")
    )
    chat.interrupt = AsyncMock(return_value=True)
    client.chat.return_value = chat
    client.widgets.respond = AsyncMock()
    client.widgets.dismiss = AsyncMock()
    client.widgets.submit_form = AsyncMock()
    client.widgets.submit_secret = AsyncMock()
    client.widgets.resolve_approval = AsyncMock()
    desktop = SimpleNamespace(
        run_state="HIBERNATED",
        connect_url=lambda: "",
        websocket_headers=lambda: {},
    )
    client.desktop = AsyncMock(return_value=desktop)
    client.get_me = AsyncMock(
        return_value=SimpleNamespace(user_id=1, email="a@b.c", first_name="A", auth_id="")
    )

    rt.client = client
    me = await rt.me()
    assert me["email"] == "a@b.c"
    agents = await rt.list_agents()
    assert agents[0]["agent_id"] == "a1"
    hist = await rt.history("a1", limit=10)
    assert hist["generation"] == 2
    assert hist["entries"][0]["text"] == "hi"
    sent = await rt.send("a1", "hello")
    assert sent["message_id"] == "m1"
    assert await rt.interrupt("a1") == {"ok": True}

    body = {"agent_id": "a1", "session_id": "", "entry_id": "w1", "kind": "form", "value": "x"}
    await rt.widget_respond(body)
    await rt.widget_dismiss(body)
    await rt.widget_submit_form({**body, "values": {"k": 1}})
    await rt.widget_submit_secret({**body, "value": "secret"})
    await rt.widget_resolve_approval({**body, "approved": True})
    client.widgets.respond.assert_awaited()
    client.widgets.resolve_approval.assert_awaited()

    desk = await rt.ensure_desktop(wake=False)
    assert desk["has_vnc"] is False
    assert desk["token"] == ""

    desktop2 = SimpleNamespace(
        run_state="RUNNING",
        connect_url=lambda: "wss://box/websockify",
        websocket_headers=lambda: {"x-anyrun-network-token": "n"},
    )
    client.desktop = AsyncMock(return_value=desktop2)
    desk2 = await rt.ensure_desktop(wake=True)
    assert desk2["has_vnc"] is True
    assert rt.vnc.take(desk2["token"]) is not None


@pytest.mark.asyncio
async def test_widget_form_values_ignore_non_dict():
    rt = Runtime()
    client = MagicMock()
    client.widgets.submit_form = AsyncMock()
    rt.client = client
    await rt.widget_submit_form(
        {"agent_id": "a", "entry_id": "e", "session_id": "", "values": "nope"}
    )
    args = client.widgets.submit_form.await_args
    assert args.args[1] == {}


@pytest.mark.asyncio
async def test_maybe_save_cursors(monkeypatch):
    saved: list = []

    def fake_save(cursors, path=None):
        saved.append(dict(cursors))

    monkeypatch.setattr("backend.runtime.save_cursors", fake_save)
    rt = Runtime()
    rt.watcher = SimpleNamespace(cursors={("a", ""): "cur"})
    rt._cursor_dirty = True
    rt._last_cursor_save = 0.0
    rt._maybe_save_cursors()
    assert saved
    assert rt._cursor_dirty is False

    rt._cursor_dirty = True
    rt._maybe_save_cursors()
    assert len(saved) == 1


@pytest.mark.asyncio
async def test_maybe_save_cursors_skips_and_logs_errors(monkeypatch):
    rt = Runtime()
    rt._cursor_dirty = False
    rt._maybe_save_cursors()
    rt._cursor_dirty = True
    rt.watcher = None
    rt._maybe_save_cursors()

    def boom(cursors, path=None):
        raise OSError("disk")

    monkeypatch.setattr("backend.runtime.save_cursors", boom)
    rt.watcher = SimpleNamespace(cursors={})
    rt._last_cursor_save = 0.0
    rt._maybe_save_cursors()
    assert rt._cursor_dirty is True


@pytest.mark.asyncio
async def test_watch_loop_records_error_then_stops(monkeypatch):
    rt = Runtime()
    rt.client = MagicMock()

    async def boom():
        raise RuntimeError("watch broke")

    monkeypatch.setattr(rt, "_run_watch", boom)

    async def sleep(_):
        rt._stop.set()

    monkeypatch.setattr("backend.runtime.asyncio.sleep", sleep)
    await rt._watch_loop()
    assert rt.last_error == "watch broke"


@pytest.mark.asyncio
async def test_watch_loop_reraises_cancelled():
    rt = Runtime()

    async def boom():
        raise asyncio.CancelledError()

    rt._run_watch = boom  # type: ignore[method-assign]
    with pytest.raises(asyncio.CancelledError):
        await rt._watch_loop()


@pytest.mark.asyncio
async def test_run_watch_broadcasts_and_persists(monkeypatch):
    from grokbot.events import Message

    saved: list = []
    monkeypatch.setattr("backend.runtime.save_cursors", lambda c, path=None: saved.append(dict(c)))
    monkeypatch.setattr("backend.runtime.load_cursors", lambda path=None: {})

    class Watcher:
        def __init__(self) -> None:
            self.cursors = {("a", ""): SimpleNamespace(agent_id="a")}
            self._done = False

        def start(self, cursors):
            self.started = cursors

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._done:
                raise StopAsyncIteration
            self._done = True
            return Message(
                agent_id="a",
                session_id="",
                entry_id="e1",
                seq=1,
                text="hi",
                role="user",
                ts=1.0,
                entry_kind="message",
                body={},
            )

    client = MagicMock()
    client.watch.return_value = Watcher()
    rt = Runtime()
    rt.client = client
    posted: list = []
    rt.hub.broadcast = AsyncMock(side_effect=lambda p: posted.append(p))  # type: ignore[method-assign]
    monkeypatch.setattr(rt, "_maybe_save_cursors", lambda: None)
    await rt._run_watch()
    assert posted[0]["type"] == "Message"
    assert saved


@pytest.mark.asyncio
async def test_start_and_stop_close_client(monkeypatch):
    closed: list[bool] = []
    stopped: list[bool] = []

    class HangWatcher:
        def __init__(self) -> None:
            self.cursors = {("a", ""): SimpleNamespace()}

        def start(self, cursors):
            return None

        def __aiter__(self):
            return self

        async def __anext__(self):
            await asyncio.Event().wait()
            raise StopAsyncIteration

        async def stop(self):
            stopped.append(True)

    class Client:
        def watch(self):
            return HangWatcher()

        async def close(self):
            closed.append(True)

    monkeypatch.setattr("backend.runtime.grokbot.GrokBotClient", lambda auth=None: Client())
    monkeypatch.setattr("backend.runtime.build_auth", lambda: object())
    monkeypatch.setattr("backend.runtime.load_cursors", lambda path=None: {})
    monkeypatch.setattr("backend.runtime.save_cursors", lambda *a, **k: None)
    rt = Runtime()
    await rt.start()
    await asyncio.sleep(0.05)
    await rt.stop()
    assert closed == [True]
    assert stopped == [True]
    with pytest.raises(AuthError, match="not signed in"):
        rt.require()


@pytest.mark.asyncio
async def test_stop_when_cursor_save_fails(monkeypatch):
    watcher = SimpleNamespace(
        cursors={("a", ""): SimpleNamespace()},
        stop=AsyncMock(),
    )

    def boom(*a, **k):
        raise OSError("disk")

    monkeypatch.setattr("backend.runtime.save_cursors", boom)
    rt = Runtime()
    rt.watcher = watcher
    client = MagicMock()
    client.close = AsyncMock()
    rt.client = client
    rt._task = asyncio.create_task(asyncio.sleep(30))
    await rt.stop()
    watcher.stop.assert_awaited()
    client.close.assert_awaited()
    assert rt.client is None


@pytest.mark.asyncio
async def test_start_without_cursor_records_error(monkeypatch):
    def boom():
        raise AuthError("nope")

    monkeypatch.setattr("backend.runtime.build_auth", boom)
    rt = Runtime()
    await rt.start()
    assert rt.client is None
    assert rt.last_error == "nope"
    with pytest.raises(AuthError, match="nope"):
        rt.require()
    await rt.stop()
