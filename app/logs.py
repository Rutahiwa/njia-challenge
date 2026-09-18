"""Structured logging. One JSON object per line, for grepping."""
from __future__ import annotations

import json
import os
from datetime import datetime

from .config import LOG_PATH

_current_run = {"run_id": None, "conversation_id": None}

LEVELS = {"debug": 10, "info": 20, "warn": 30, "error": 40}


def bind(run_id: str, conversation_id: str) -> None:
    _current_run["run_id"] = run_id
    _current_run["conversation_id"] = conversation_id


def _write(level: str, event: str, **fields) -> None:
    entry = {
        "ts": datetime.now().isoformat(),
        "level": level,
        "event": event,
        "run_id": _current_run["run_id"],
        "conversation_id": _current_run["conversation_id"],
    }
    entry.update(fields)
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "a") as handle:
        handle.write(json.dumps(entry, indent=2) + "\n")


def info(event: str, **fields) -> None:
    _write("info", event, **fields)


def warn(event: str, **fields) -> None:
    _write("warn", event, **fields)


def error(event: str, exc: Exception | None = None, **fields) -> None:
    if exc is not None:
        fields.setdefault("code", getattr(exc, "code", ""))
        fields["detail"] = str(exc)
    _write("warn", event, **fields)
