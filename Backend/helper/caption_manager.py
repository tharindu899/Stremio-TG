from __future__ import annotations

from asyncio import CancelledError, Queue, create_task
from html import escape
from time import monotonic

from pyrogram.enums import ParseMode

from Backend.helper.caption_tools import preferred_caption_filename
from Backend.helper.settings_manager import SettingsManager
from Backend.helper.task_manager import edit_message
from Backend.logger import LOGGER

# Caption edits are deliberately serialized. Bulk channel uploads can deliver
# hundreds of updates at once; editing each one in a separate task causes
# Telegram FloodWait errors and duplicate edited-message callbacks.
_caption_queue: Queue[tuple[int, int, str]] = Queue()
_pending: set[tuple[int, int]] = set()
_recent: dict[tuple[int, int], float] = {}
_worker_task = None
_RECENT_TTL_SECONDS = 15.0


def get_message_filename(message) -> str:
    """Return the real Telegram filename for a document/video message."""
    media = getattr(message, "video", None) or getattr(message, "document", None)
    return str(getattr(media, "file_name", "") or "").strip()


def _utf16_length(value: str) -> int:
    # Telegram entity offsets/lengths are counted as UTF-16 code units.
    return len(value.encode("utf-16-le")) // 2


def _entity_is_bold(entity) -> bool:
    entity_type = getattr(entity, "type", None)
    value = getattr(entity_type, "value", entity_type)
    return str(value or "").lower() == "bold"


def has_exact_bold_filename_caption(message, filename: str) -> bool:
    """True when caption text is only filename and the whole caption is bold."""
    if str(getattr(message, "caption", "") or "") != filename:
        return False

    expected_length = _utf16_length(filename)
    for entity in getattr(message, "caption_entities", None) or []:
        if (
            _entity_is_bold(entity)
            and int(getattr(entity, "offset", -1)) == 0
            and int(getattr(entity, "length", -1)) == expected_length
        ):
            return True
    return False


def _prune_recent(now: float) -> None:
    if len(_recent) < 500:
        return
    expired = [key for key, when in _recent.items() if now - when >= _RECENT_TTL_SECONDS]
    for key in expired:
        _recent.pop(key, None)


def _ensure_worker() -> None:
    global _worker_task
    if _worker_task is None or _worker_task.done():
        _worker_task = create_task(_caption_worker(), name="filename-caption-worker")


async def apply_filename_caption(message) -> bool:
    """
    Queue replacement of any existing caption with the exact filename in bold.

    Returns True when a new edit was queued. The setting is read at execution
    time too, so switching it OFF immediately stops pending edits.
    """
    if not SettingsManager.current().auto_filename_caption:
        return False

    real_filename = get_message_filename(message)
    if not real_filename:
        return False

    filename = preferred_caption_filename(
        getattr(message, "caption", "") or "",
        real_filename,
    )
    # Non-empty custom captions without a detectable filename are deliberately
    # preserved exactly as the uploader wrote them.
    if not filename:
        return False

    if has_exact_bold_filename_caption(message, filename):
        return False

    chat = getattr(message, "chat", None)
    chat_id = getattr(chat, "id", None)
    msg_id = getattr(message, "id", None)
    if chat_id is None or msg_id is None:
        return False

    key = (int(chat_id), int(msg_id))
    now = monotonic()
    _prune_recent(now)

    # The caption edit itself emits an edited-message update. Suppress that
    # echo and any duplicate handler invocations for a short window.
    if key in _pending or now - _recent.get(key, 0.0) < _RECENT_TTL_SECONDS:
        return False

    _pending.add(key)
    _caption_queue.put_nowait((key[0], key[1], filename))
    _ensure_worker()
    return True


async def _caption_worker() -> None:
    while True:
        chat_id, msg_id, filename = await _caption_queue.get()
        key = (chat_id, msg_id)
        attempted = False
        try:
            # Respect an OFF toggle even for jobs queued a moment earlier.
            if not SettingsManager.current().auto_filename_caption:
                continue

            attempted = True
            edited = await edit_message(
                chat_id,
                msg_id,
                f"<b>{escape(filename)}</b>",
                parse_mode=ParseMode.HTML,
            )
            if edited:
                LOGGER.info(f"[Caption] Set bold filename caption for message {msg_id}: {filename}")
        except CancelledError:
            raise
        except Exception as exc:
            LOGGER.warning(
                f"[Caption] Could not set filename caption on message {msg_id}: {exc}"
            )
        finally:
            _pending.discard(key)
            if attempted:
                _recent[key] = monotonic()
            _caption_queue.task_done()
