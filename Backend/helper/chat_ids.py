"""Telegram channel ID normalization helpers.

Indexed stream tokens in this project historically store only the numeric
channel suffix (for example ``3705440783``), while Pyrogram requires the full
Telegram peer ID (for example ``-1003705440783``).  Accept both forms at every
boundary so older rows and mover-created rows remain playable.
"""

from __future__ import annotations

from typing import Any


def to_telegram_chat_id(value: Any) -> int:
    """Return a numeric Telegram peer ID suitable for Pyrogram calls."""
    text = str(value or "").strip()
    if not text:
        raise ValueError("Missing Telegram channel ID")

    chat_id = int(text)
    if chat_id < 0:
        return chat_id
    return int(f"-100{chat_id}")


def to_stored_chat_id(value: Any) -> int:
    """Return the canonical compact channel ID stored in stream payloads."""
    text = str(value or "").strip()
    if not text:
        raise ValueError("Missing Telegram channel ID")

    if text.startswith("-100") and len(text) > 4:
        suffix = text[4:]
        if suffix.isdigit():
            return int(suffix)

    chat_id = int(text)
    if chat_id >= 0:
        return chat_id

    # Non-channel negative peers are retained as-is for compatibility. AUTH
    # media destinations are channels and therefore normally use -100 IDs.
    return chat_id
