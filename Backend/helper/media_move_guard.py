"""Short-lived guards that prevent mover-created Telegram posts being re-indexed.

The WebUI mover copies existing channel messages and updates the stored MongoDB
references itself.  Those copies must not enter the normal upload receiver,
otherwise Replace Mode treats them as new uploads and may delete the original
posts before the title-level transaction is complete.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from time import monotonic
from typing import Iterable

_CHANNEL_GUARDS: dict[int, int] = {}
_MESSAGE_GUARDS: dict[tuple[int, int], float] = {}
_DEFAULT_MESSAGE_TTL = 600.0


def _cleanup() -> None:
    now = monotonic()
    for key, expiry in list(_MESSAGE_GUARDS.items()):
        if expiry <= now:
            _MESSAGE_GUARDS.pop(key, None)


def mark_mover_message(chat_id: int, message_id: int, ttl: float = _DEFAULT_MESSAGE_TTL) -> None:
    """Remember an exact destination post long enough for delayed updates."""
    _cleanup()
    _MESSAGE_GUARDS[(int(chat_id), int(message_id))] = monotonic() + max(30.0, float(ttl))


def is_mover_message(chat_id: int, message_id: int | None = None) -> bool:
    """Return True while a channel or exact Telegram message is mover-owned."""
    _cleanup()
    normalized_chat = int(chat_id)
    if _CHANNEL_GUARDS.get(normalized_chat, 0) > 0:
        return True
    if message_id is None:
        return False
    return (normalized_chat, int(message_id)) in _MESSAGE_GUARDS


@asynccontextmanager
async def suppress_move_destination(chat_ids: int | Iterable[int]):
    """Suppress normal upload indexing for one or more move destinations."""
    if isinstance(chat_ids, int):
        normalized = [int(chat_ids)]
    else:
        normalized = sorted({int(value) for value in chat_ids})

    for chat_id in normalized:
        _CHANNEL_GUARDS[chat_id] = _CHANNEL_GUARDS.get(chat_id, 0) + 1
    try:
        yield
    finally:
        for chat_id in normalized:
            remaining = _CHANNEL_GUARDS.get(chat_id, 0) - 1
            if remaining > 0:
                _CHANNEL_GUARDS[chat_id] = remaining
            else:
                _CHANNEL_GUARDS.pop(chat_id, None)
