from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from project.logs.logger import append_log


_ANSI_ESCAPE_RE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")


def _clean_dialogue_text(text: str) -> str:
    """Remove terminal control sequences and unwrap accidental newlines.

    Some CLI backends (e.g., model CLIs) can emit ANSI cursor/clear codes when
    stdout is captured. Those should never appear in stored dialogue.
    """
    text = _ANSI_ESCAPE_RE.sub("", text)
    text = text.replace("\r", "")
    # Replace newlines with spaces so accidental line-wraps don't split words.
    text = text.replace("\n", " ")
    # Collapse excessive whitespace.
    text = re.sub(r"\s+", " ", text).strip()
    return text


def log_event(
    log_file: Path,
    *,
    event: str,
    payload: Dict[str, Any],
    source: str = "cli",
) -> None:
    """Append a typed event to the runtime log.

    The log is a JSONL file written via project.logs.logger.append_log, which adds `ts`.
    """
    append_log(
        log_file,
        {
            "event": event,
            "source": source,
            **payload,
        },
    )


def read_events(
    log_file: Path,
    *,
    event_types: Optional[Sequence[str]] = None,
    max_events: int = 500,
) -> List[Dict[str, Any]]:
    """Read events from a JSONL runtime log.

    Returns events in file order (oldest -> newest) capped to the most recent `max_events`.
    """
    if not log_file.exists():
        return []

    allowed = set(event_types) if event_types is not None else None
    out: List[Dict[str, Any]] = []

    try:
        for line in log_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue

            etype = obj.get("event")
            if not isinstance(etype, str) or not etype:
                continue
            if allowed is not None and etype not in allowed:
                continue

            out.append(obj)

        if len(out) > max_events:
            out = out[-max_events:]
    except Exception:
        return []

    return out


def _only_dicts(items: Iterable[Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            out.append(item)
    return out


# --- Convenience helpers (evidence / dialogue / options) ---

def log_evidence(log_file: Path, *, title: str, description: str, source: str = "cli") -> None:
    log_event(
        log_file,
        event="evidence",
        payload={"title": title, "description": description},
        source=source,
    )


def read_evidence_events(
    log_file: Path,
    *,
    max_events: int = 200,
) -> List[Dict[str, Any]]:
    events = read_events(log_file, event_types=["evidence"], max_events=max_events)
    # Keep only well-formed evidence events for callers that expect these keys.
    out: List[Dict[str, Any]] = []
    for ev in events:
        title = ev.get("title")
        description = ev.get("description")
        if isinstance(title, str) and title and isinstance(description, str) and description:
            out.append(ev)
    return out


def log_dialogue(log_file: Path, *, speaker: str, text: str, source: str = "cli") -> None:
    log_event(
        log_file,
        event="dialogue",
        payload={"speaker": speaker, "text": _clean_dialogue_text(text)},
        source=source,
    )


def read_dialogue_events(
    log_file: Path,
    *,
    max_events: int = 500,
) -> List[Dict[str, Any]]:
    events = read_events(log_file, event_types=["dialogue"], max_events=max_events)
    out: List[Dict[str, Any]] = []
    for ev in events:
        speaker = ev.get("speaker")
        text = ev.get("text")
        if isinstance(speaker, str) and speaker and isinstance(text, str) and text:
            ev2 = dict(ev)
            ev2["text"] = _clean_dialogue_text(text)
            out.append(ev2)
    return out


def log_argument_options(
    log_file: Path,
    *,
    options: Sequence[Dict[str, Any]],
    source: str = "cli",
) -> None:
    # options should be JSON-serializable dicts.
    log_event(
        log_file,
        event="argument_options",
        payload={"options": list(options)},
        source=source,
    )


def read_argument_options_events(
    log_file: Path,
    *,
    max_events: int = 50,
) -> List[Dict[str, Any]]:
    events = read_events(log_file, event_types=["argument_options"], max_events=max_events)
    out: List[Dict[str, Any]] = []
    for ev in events:
        options = ev.get("options")
        if isinstance(options, list):
            ev2 = dict(ev)
            ev2["options"] = _only_dicts(options)
            out.append(ev2)
    return out

def log_statement(
    log_file: Path,
    *,
    statement_id: str,
    text: str,
    source: str = "cli",
) -> None:
    log_event(
        log_file,
        event="statement",
        payload={"id": statement_id, "text": _clean_dialogue_text(text)},
        source=source,
    )

def read_statement_events(
    log_file: Path,
    *,
    max_events: int = 50,
) -> List[Dict[str, Any]]:
    events = read_events(log_file, event_types=["statement"], max_events=max_events)
    return events

def reset_log_events(log_file: Path) -> None:
    """Delete all stored events by truncating the JSONL log file."""
    log_file.parent.mkdir(parents=True, exist_ok=True)
    # Truncate the file (or create it if missing).
    with log_file.open("w", encoding="utf-8"):
        pass

def log_input(
    log_file: Path,
    *,
    input_type: str,
    input_value: str,
    source: str = "cli",
) -> None:
    log_event(
        log_file,
        event="user_input",
        payload={"type": input_type, "value": input_value},
        source=source,
)

def read_input_events(
    log_file: Path,
    *,
    max_events: int = 50,
) -> str:
    events = read_events(log_file, event_types=["user_input"], max_events=max_events)
    out = ""
    for ev in events:
        out=ev.get("value")
    return out