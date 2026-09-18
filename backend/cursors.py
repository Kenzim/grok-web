"""Persist TranscriptWatcher.cursors across process restarts."""

from __future__ import annotations

import json
from pathlib import Path

from grokbot.models import TranscriptCursor

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PATH = ROOT / "data" / "cursors.json"


def load_cursors(path: Path | None = None) -> dict[tuple[str, str], TranscriptCursor]:
    target = path or DEFAULT_PATH
    try:
        raw = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    rows = raw if isinstance(raw, list) else []
    out: dict[tuple[str, str], TranscriptCursor] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        cur = TranscriptCursor(
            agent_id=str(row.get("agent_id") or ""),
            session_id=str(row.get("session_id") or ""),
            generation=int(row.get("generation") or 0),
            after_updated_seq=int(row.get("after_updated_seq") or 0),
        )
        out[cur.key] = cur
    return out


def save_cursors(
    cursors: dict[tuple[str, str], TranscriptCursor], path: Path | None = None
) -> None:
    target = path or DEFAULT_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {
            "agent_id": cur.agent_id,
            "session_id": cur.session_id,
            "generation": cur.generation,
            "after_updated_seq": cur.after_updated_seq,
        }
        for cur in cursors.values()
    ]
    target.write_text(json.dumps(rows, indent=2), encoding="utf-8")
