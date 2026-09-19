"""Which language to answer in."""
from __future__ import annotations

import re

SWAHILI_WORDS = [
    "nataka", "basi", "kiti", "tiketi", "safari", "asante", "habari",
    "bei", "lini", "kesho", "ndiyo", "hapana",
    "nauli", "malipo", "abiria", "kituo", "kwenda", "kutoka", "tarehe",
    "saa", "asubuhi", "usiku", "leo", "shilingi", "tafadhali",
    "samahani", "naomba", "nafasi", "jina", "namba", "karibu",
]

_last_language: dict[str, str] = {}


def clean(text: str) -> str:
    return re.sub(r"[^a-z ]", "", text.lower())


def detect(conversation_id: str, messages: list[str]) -> str:
    """Return 'sw' or 'en' for the conversation."""
    if not messages:
        return _last_language.get(conversation_id, "en")

    joined = clean(" ".join(messages))
    words = set(joined.split())
    for word in SWAHILI_WORDS:
        if word in words:
            _last_language[conversation_id] = "sw"
            return "sw"

    _last_language[conversation_id] = "en"
    return "en"


def instruction(language: str) -> str:
    if language == "sw":
        return "Reply in Kiswahili."
    return "Reply in English."
