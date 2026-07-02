"""Low-priority, one-line owner-PM status messages for live uploads."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Any

from pyrogram.errors import FloodWait

from Backend.config import Telegram
from Backend.helper.settings_manager import SettingsManager
from Backend.logger import LOGGER


_STATUS_QUEUE_LIMIT = 5000
_STATUS_SEND_INTERVAL_SECONDS = 0.40


@dataclass(slots=True)
class UploadStatus:
    client: Any
    recipient_id: int
    text: str


_status_queue: asyncio.Queue[UploadStatus] = asyncio.Queue(maxsize=_STATUS_QUEUE_LIMIT)


def _filename(value: object) -> str:
    """Keep the original Telegram filename on a single safe line."""
    name = " ".join(str(value or "").replace("\x00", "").split())
    return name or "Unknown file"


def format_upload_status(
    *,
    kind: str,
    state: str,
    action: str,
    title: object,
    detail: object = "",
) -> str:
    """Return the fixed compact status format used in the owner PM."""
    del action, detail

    kind_key = " ".join(str(kind or "").split()).casefold()
    state_key = " ".join(str(state or "").split()).casefold()

    if state_key == "skipped":
        prefix = "⏭️ skipped"
    elif state_key == "warning" and kind_key == "subtitle":
        prefix = "⚠️ Sub pending"
    elif state_key == "success" and kind_key == "split":
        prefix = "✅ Split"
    elif state_key == "success" and kind_key == "subtitle":
        prefix = "✅ Subtitle"
    elif state_key == "success" and kind_key == "video":
        prefix = "✅ Video"
    else:
        prefix = "❌ Metadata/index"

    return f"{prefix} : {_filename(title)}"


async def queue_upload_status(
    *,
    client: Any,
    chat_id: int,
    reply_to_message_id: int,
    kind: str,
    state: str,
    action: str,
    title: object,
    detail: object = "",
) -> None:
    """Queue an owner PM without making channel indexing wait for Telegram.

    ``chat_id`` and ``reply_to_message_id`` remain accepted so upload handlers
    can use one stable call shape. They are intentionally ignored: no message
    is posted or replied to in the source channel.
    """
    del chat_id, reply_to_message_id

    if not SettingsManager.current().upload_status_messages:
        return

    owner_id = int(Telegram.OWNER_ID or 0)
    if owner_id <= 0:
        return

    status = UploadStatus(
        client=client,
        recipient_id=owner_id,
        text=format_upload_status(
            kind=kind,
            state=state,
            action=action,
            title=title,
            detail=detail,
        ),
    )
    try:
        _status_queue.put_nowait(status)
    except asyncio.QueueFull:
        LOGGER.warning("[UploadStatus] Queue full; owner PM status dropped.")


async def _send_status(status: UploadStatus) -> None:
    """Send the compact status only to the configured owner in private chat."""
    try:
        await status.client.send_message(
            chat_id=status.recipient_id,
            text=status.text,
            disable_web_page_preview=True,
        )
        return
    except FloodWait as exc:
        await asyncio.sleep(max(1, int(exc.value)))

    await status.client.send_message(
        chat_id=status.recipient_id,
        text=status.text,
        disable_web_page_preview=True,
    )


async def process_upload_statuses() -> None:
    """Deliver owner PMs serially so Telegram traffic never blocks indexing."""
    last_sent_at = 0.0
    while True:
        status = await _status_queue.get()
        try:
            wait_for = _STATUS_SEND_INTERVAL_SECONDS - (monotonic() - last_sent_at)
            if wait_for > 0:
                await asyncio.sleep(wait_for)
            await _send_status(status)
            last_sent_at = monotonic()
        except Exception as exc:
            LOGGER.warning("[UploadStatus] Owner PM delivery failed: %s", exc)
        finally:
            _status_queue.task_done()
