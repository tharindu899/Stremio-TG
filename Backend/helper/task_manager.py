from asyncio import Lock, sleep
from typing import List

from pyrogram.errors import (
    FloodWait,
    ChatAdminRequired,
    ChannelPrivate,
    MessageDeleteForbidden,
    MessageAuthorRequired,
    MessageIdInvalid,
    MessageNotModified,
    PeerIdInvalid,
    UserNotParticipant,
    AuthKeyUnregistered,
    SessionRevoked,
)

from Backend.logger import LOGGER
from Backend.pyrofork.bot import StreamBot, Userbot

DELETE_BATCH_SIZE = 10
_EDIT_DELAY_SECONDS = 2.1
_EDIT_MAX_RETRIES = 3
_edit_lock = Lock()
_FALLBACK_WORTHY = (
    ChatAdminRequired,
    ChannelPrivate,
    MessageDeleteForbidden,
    MessageAuthorRequired,
    PeerIdInvalid,
    UserNotParticipant,
)
_SESSION_DEAD = (AuthKeyUnregistered, SessionRevoked)
_userbot_session_dead = False


def _userbot_usable() -> bool:
    return Userbot is not None and not _userbot_session_dead


async def _edit_with_client(client, label: str, chat_id: int, msg_id: int, new_caption: str, parse_mode=None):
    """Return True on success/already-done, None for permission fallback, False otherwise."""
    global _userbot_session_dead

    for attempt in range(1, _EDIT_MAX_RETRIES + 1):
        try:
            await client.edit_message_caption(
                chat_id=chat_id,
                message_id=msg_id,
                caption=new_caption,
                parse_mode=parse_mode,
            )
            # Keep all caption edits below Telegram's burst threshold.
            await sleep(_EDIT_DELAY_SECONDS)
            return True
        except MessageNotModified:
            # A duplicate edited-message callback may arrive after the first edit.
            return True
        except MessageIdInvalid:
            # The source message was normally deleted/replaced before its queued
            # caption edit ran. A userbot retry cannot restore a missing ID.
            LOGGER.debug(f"[{label}] Skipped unavailable message {msg_id} in {chat_id}")
            return False
        except FloodWait as exc:
            wait_for = max(1, int(getattr(exc, "value", 1))) + 1
            LOGGER.warning(
                f"[{label}] FloodWait {wait_for - 1}s while editing message {msg_id} "
                f"in {chat_id} (attempt {attempt}/{_EDIT_MAX_RETRIES})"
            )
            await sleep(wait_for)
            if attempt == _EDIT_MAX_RETRIES:
                return False
        except _SESSION_DEAD as exc:
            if label == "USERBOT":
                _userbot_session_dead = True
            LOGGER.error(
                f"[{label}] Session invalid ({type(exc).__name__}): {exc}"
            )
            return False
        except _FALLBACK_WORTHY as exc:
            LOGGER.info(
                f"[{label}] Cannot edit message {msg_id} in {chat_id} "
                f"({type(exc).__name__}); trying fallback"
            )
            return None
        except Exception as exc:
            LOGGER.error(
                f"[{label}] Error while editing message {msg_id} in {chat_id}: {exc}"
            )
            return False

    return False


#----- Edit a message caption via StreamBot, falling back to the Userbot.
#----- A global lock prevents concurrent edit bursts from bulk channel uploads.
async def edit_message(chat_id: int, msg_id: int, new_caption: str, parse_mode=None):
    async with _edit_lock:
        result = await _edit_with_client(
            StreamBot, "STREAMBOT", chat_id, msg_id, new_caption, parse_mode=parse_mode
        )
        if result is not None:
            return result

        if not _userbot_usable():
            return False

        return bool(await _edit_with_client(
            Userbot, "USERBOT", chat_id, msg_id, new_caption, parse_mode=parse_mode
        ))


async def delete_message(chat_id: int, msg_id: int):
    await delete_messages_batch(chat_id, [msg_id])


#----- Delete messages in batches, using the Userbot fallback for leftovers
async def delete_messages_batch(chat_id: int, msg_ids: List[int]):
    if not msg_ids:
        return

    for i in range(0, len(msg_ids), DELETE_BATCH_SIZE):
        chunk = msg_ids[i:i + DELETE_BATCH_SIZE]

        remaining = await _delete_chunk(StreamBot, "StreamBot", chat_id, chunk)

        if remaining and _userbot_usable():
            LOGGER.info(f"[USERBOT] Fallback triggered: deleting {len(remaining)} message(s) in {chat_id}")
            remaining = await _delete_chunk(Userbot, "Userbot", chat_id, remaining)

        if remaining:
            LOGGER.error(
                f"Could not delete {len(remaining)} message(s) in {chat_id} "
                f"(no usable Userbot fallback)" if not _userbot_usable() else
                f"Could not delete {len(remaining)} message(s) in {chat_id} even with Userbot fallback"
            )

        await sleep(1)


async def _delete_chunk(client, client_label: str, chat_id: int, msg_ids: List[int]) -> List[int]:
    global _userbot_session_dead
    try:
        await client.delete_messages(chat_id=chat_id, message_ids=msg_ids)
        LOGGER.info(f"[{client_label.upper()}] Deleted {len(msg_ids)} message(s) in {chat_id}")
        return []
    except FloodWait as e:
        LOGGER.warning(f"[{client_label.upper()}] FloodWait detected: sleeping {e.value}s ({len(msg_ids)} msg(s) in {chat_id})")
        await sleep(e.value)
        try:
            await client.delete_messages(chat_id=chat_id, message_ids=msg_ids)
            LOGGER.info(f"[{client_label.upper()}] Deleted {len(msg_ids)} message(s) in {chat_id} after FloodWait retry")
            return []
        except Exception as e2:
            LOGGER.error(f"[{client_label.upper()}] Retry after FloodWait failed in {chat_id}: {e2}")
            return msg_ids
    except _SESSION_DEAD as e:
        if client_label == "Userbot":
            _userbot_session_dead = True
        LOGGER.error(f"[{client_label.upper()}] Session invalid ({type(e).__name__}): {e}")
        return msg_ids
    except _FALLBACK_WORTHY as e:
        LOGGER.warning(f"[{client_label.upper()}] Cannot delete in {chat_id} ({type(e).__name__}): {e}")
        return msg_ids
    except Exception as e:
        LOGGER.error(f"[{client_label.upper()}] Unexpected error deleting in {chat_id}: {e}")
        return msg_ids
