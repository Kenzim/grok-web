from pathlib import Path

from backend.cursors import load_cursors, save_cursors
from grokbot.models import TranscriptCursor


def test_cursor_round_trip_includes_empty_session(tmp_path: Path):
    path = tmp_path / "cursors.json"
    original = {
        ("agent-a", ""): TranscriptCursor(
            agent_id="agent-a",
            session_id="",
            generation=2,
            after_updated_seq=44,
        ),
        ("agent-b", "sess"): TranscriptCursor(
            agent_id="agent-b",
            session_id="sess",
            generation=1,
            after_updated_seq=9,
        ),
    }
    save_cursors(original, path)
    loaded = load_cursors(path)
    assert set(loaded) == set(original)
    assert loaded[("agent-a", "")].generation == 2
    assert loaded[("agent-a", "")].after_updated_seq == 44
    assert loaded[("agent-b", "sess")].session_id == "sess"


def test_missing_file_is_empty(tmp_path: Path):
    assert load_cursors(tmp_path / "missing.json") == {}


def test_corrupt_and_non_list_payloads(tmp_path: Path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")
    assert load_cursors(bad) == {}
    obj = tmp_path / "obj.json"
    obj.write_text('{"agent_id": "x"}', encoding="utf-8")
    assert load_cursors(obj) == {}
    mixed = tmp_path / "mixed.json"
    mixed.write_text(
        '[{"agent_id": "a"}, "skip", {"session_id": "s", "generation": "3"}]',
        encoding="utf-8",
    )
    loaded = load_cursors(mixed)
    assert ("a", "") in loaded
    assert loaded[("a", "")].generation == 0
    assert loaded[("", "s")].generation == 3


def test_save_creates_parent_dir(tmp_path: Path):
    path = tmp_path / "nested" / "cursors.json"
    save_cursors({}, path)
    assert path.is_file()
    assert load_cursors(path) == {}
