from backend.serialize import (
    account_json,
    agent_json,
    entry_json,
    event_json,
    json_safe,
    receipt_json,
)
from grokbot.events import (
    AgentStateUpdate,
    BoxStateChanged,
    ComputerActions,
    HandoffRequested,
    Message,
    RosterChanged,
    StreamReset,
    TurnFailed,
    WidgetRequest,
)
from grokbot.models import Account, Agent, SendReceipt, TranscriptEntry


def test_json_safe_drops_bytes_garbage_and_dicts():
    assert json_safe({"a": 1, "b": b"hi"}) == {"a": 1, "b": "hi"}
    assert json_safe((1, "x")) == [1, "x"]


def test_account_and_agent_omit_raw():
    account = Account(user_id=1, email="a@b.c", first_name="A", raw=object())
    agent = Agent(
        id="1",
        agent_id="uuid",
        name="job finder",
        description="",
        harness="box",
        kind="DEFAULT",
        created_at_ms=1,
        raw=object(),
    )
    assert "raw" not in account_json(account)
    out = agent_json(agent)
    assert out["agent_id"] == "uuid"
    assert out["harness"] == "box"
    assert "raw" not in out


def test_receipt_json():
    rec = SendReceipt(message_id="m1", dispatched=True, delivery="ACCEPTED_BOX", raw=object())
    assert receipt_json(rec) == {
        "message_id": "m1",
        "dispatched": True,
        "delivery": "ACCEPTED_BOX",
        "workflow_id": None,
    }


def test_event_json_message_and_widget():
    msg = Message(
        agent_id="a",
        session_id="",
        entry_id="e1",
        seq=3,
        text="hello",
        role="user",
        ts=1.5,
        entry_kind="message",
        body={"content": "hello"},
    )
    out = event_json(msg)
    assert out["type"] == "Message"
    assert out["text"] == "hello"
    assert out["body"]["content"] == "hello"

    widget = WidgetRequest(
        agent_id="a",
        session_id="",
        entry_id="w1",
        kind="approval",
        prompt="Allow?",
        request_id="r1",
        body={"prompt": "Allow?"},
    )
    wout = event_json(widget)
    assert wout["type"] == "WidgetRequest"
    assert wout["prompt"] == "Allow?"
    assert "raw" not in wout


def test_event_json_strips_proto_like_fields():
    handoff = HandoffRequested(
        agent_id="a",
        session_id="",
        request_id="h1",
        instruction="solve captcha",
        reason="captcha",
        tab_id="t1",
    )
    assert event_json(handoff)["type"] == "HandoffRequested"
    assert event_json(AgentStateUpdate("a", "", True, False, live_state=object())) == {
        "type": "AgentStateUpdate",
        "agent_id": "a",
        "session_id": "",
        "is_running": True,
        "is_composing": False,
    }
    assert event_json(BoxStateChanged("RUNNING", raw=object())) == {
        "type": "BoxStateChanged",
        "run_state": "RUNNING",
    }
    assert event_json(ComputerActions("a", actions=[object()])) == {
        "type": "ComputerActions",
        "agent_id": "a",
        "actions": [],
    }


def test_entry_json_user_and_assistant_and_widget():
    user = TranscriptEntry(
        seq=1,
        entry_kind="message",
        entry_id="u1",
        body={"kind": "message", "role": "user", "content": "hi", "timestampMs": 1000},
        body_raw=None,
        blob_hash=None,
        body_omitted=False,
        updated_seq=1,
        raw=object(),
    )
    uout = entry_json("agent", "", user)
    assert uout["role"] == "user"
    assert uout["text"] == "hi"
    assert "raw" not in uout

    assistant = TranscriptEntry(
        seq=2,
        entry_kind="send-message",
        entry_id="a1",
        body={"message": {"type": "text", "content": "ok"}},
        body_raw=None,
        blob_hash=None,
        body_omitted=False,
        updated_seq=2,
    )
    aout = entry_json("agent", "", assistant)
    assert aout["role"] == "assistant"
    assert aout["text"] == "ok"

    widget = TranscriptEntry(
        seq=3,
        entry_kind="send-message",
        entry_id="w1",
        body={
            "message": {
                "type": "widget",
                "widget": {"type": "approval", "prompt": "Continue?"},
            }
        },
        body_raw=None,
        blob_hash=None,
        body_omitted=False,
        updated_seq=3,
    )
    wout = entry_json("agent", "", widget)
    assert wout["widget"]["kind"] == "approval"
    assert wout["widget"]["prompt"] == "Continue?"


def test_images_skip_file_urls_and_keep_https():
    entry = TranscriptEntry(
        seq=4,
        entry_kind="send-message",
        entry_id="img",
        body={
            "message": {
                "type": "text",
                "content": "pic",
                "images": [
                    {"url": "file:///tmp/x.png"},
                    {"src": "https://cdn.example/a.png", "alt": "a"},
                    "nope",
                ],
            }
        },
        body_raw=None,
        blob_hash=None,
        body_omitted=False,
        updated_seq=4,
    )
    out = entry_json("agent", "", entry)
    assert out["images"] == [{"url": "https://cdn.example/a.png", "alt": "a"}]


def test_json_safe_invalid_utf8_and_unknown():
    assert json_safe(b"\xff") is None
    assert json_safe(object()).startswith("<")
    class FakeProto:
        DESCRIPTOR = object()
    assert json_safe(FakeProto()) is None


def test_event_json_roster_turn_reset_and_unknown():
    assert event_json(RosterChanged(kind="ADDED", agent_id="a"))["type"] == "RosterChanged"
    failed = event_json(TurnFailed("a", "", "boom", code="X", turn_id="t"))
    assert failed["reason"] == "boom"
    assert event_json(StreamReset("a", "", "cleared"))["reason"] == "cleared"
    assert event_json(object()) == {"type": "object"}


def test_json_safe_dataclass_and_nested():
    from dataclasses import dataclass

    @dataclass
    class Box:
        x: int
        raw: object
        live_state: object = None

    assert json_safe(Box(1, object(), object())) == {"x": 1}
    assert json_safe({"n": [1, {"k": True}]}) == {"n": [1, {"k": True}]}


def test_images_from_top_level_body_and_empty():
    top = TranscriptEntry(
        seq=1,
        entry_kind="send-message",
        entry_id="img",
        body={"images": [{"url": "https://cdn.example/b.png"}, {"url": ""}]},
        body_raw=None,
        blob_hash=None,
        body_omitted=False,
        updated_seq=1,
    )
    assert entry_json("a", "", top)["images"] == [{"url": "https://cdn.example/b.png", "alt": ""}]
    empty = TranscriptEntry(
        seq=2,
        entry_kind="message",
        entry_id="e",
        body=["not", "a", "dict"],
        body_raw=None,
        blob_hash=None,
        body_omitted=False,
        updated_seq=2,
    )
    assert entry_json("a", "", empty)["images"] == []
