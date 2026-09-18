"""Which language to answer in."""
from __future__ import annotations

import re

SWAHILI_WORDS = [
    "nataka", "basi", "kiti", "tiketi", "safari", "asante", "habari",
    "bei", "lini", "kesho", "ndiyo", "hapana",
]

_last_language: dict[str, str] = {}


def clean(text: str) -> str:
    return re.sub(r"[^a-z ]", "", text.lower())


def detect(conversation_id: str, messages: list[str]) -> str:
    """Return 'sw' or 'en' for the conversation."""
    if conversation_id in _last_language:
        return _last_language[conversation_id]

    joined = clean(" ".join(messages))
    for word in SWAHILI_WORDS:
        if word in joined:
            _last_language[conversation_id] = "sw"
            return "sw"

    _last_language[conversation_id] = "en"
    return "en"


def instruction(language: str) -> str:
    if language == "sw":
        return "Reply in Kiswahili."
    return "Reply in English."
