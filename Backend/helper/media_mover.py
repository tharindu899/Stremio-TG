"""Transactional Telegram media moves used by the Media → Edit workspace.

A move follows a copy-first sequence:
1. Copy every Telegram source message to the selected configured channel.
2. Replace the stream references in MongoDB.
3. Delete the old Telegram source messages.

Mover-created copies bypass normal upload indexing. The old posts are never
removed before the replacement references are safely saved. If copying or saving
fails, any new copies are cleaned up and the existing stream remains unchanged.
"""

from __future__ import annotations

import asyncio
import os
import re
import tempfile
from collections import defaultdict
from copy import deepcopy
from datetime import datetime
from time import monotonic
from typing import Any, Awaitable, Callable, Iterable
from uuid import uuid4

from pyrogram.errors import FloodWait

from Backend.helper.encrypt import decode_string, encode_string
from Backend.helper.chat_ids import to_stored_chat_id
from Backend.helper.settings_manager import SettingsManager
from Backend.helper.task_manager import delete_messages_batch
from Backend.helper.telegram_sessions import userbot_is_usable
from Backend.helper.media_move_guard import mark_mover_message, suppress_move_destination
from Backend.logger import LOGGER
from Backend.pyrofork.bot import StreamBot, Userbot, multi_clients


class MediaMoveError(RuntimeError):
    """User-facing failure while moving an indexed Telegram stream."""


_COPY_CLIENT_CURSOR = 0
_COPY_LOCK = asyncio.Lock()
_LAST_FLOOD_LOG_AT = 0.0
_FLOOD_LOG_INTERVAL_SECONDS = 60.0

# Full-title moves are deliberately throttled. Telegram applies limits per
# account and per destination channel, so rotating clients without a shared
# cooldown can still trigger FloodWait. All mover copies pass through one lock
# and pause after each successful message.
try:
    _COPY_DELAY_SECONDS = max(2.0, float(os.getenv("MEDIA_MOVE_COPY_DELAY_SECONDS", "3")))
except (TypeError, ValueError):
    _COPY_DELAY_SECONDS = 3.0


def _peer(value: Any) -> int | str:
    text = str(value or "").strip()
    if not text:
        raise MediaMoveError("Choose a destination channel.")
    return int(text) if text.lstrip("-").isdigit() else text


def _available_clients() -> list[Any]:
    """Return unique Telegram clients that are currently connected."""
    clients: list[Any] = []
    seen: set[int] = set()

    def add(client: Any) -> None:
        if client is None or id(client) in seen:
            return
        # Pyrogram exposes is_connected after start(). Treat an explicit False
        # as unavailable, but keep compatibility with test doubles that do not
        # implement the property.
        if getattr(client, "is_connected", None) is False:
            return
        seen.add(id(client))
        clients.append(client)

    add(StreamBot)
    for client in multi_clients.values():
        add(client)
    if userbot_is_usable(Userbot):
        add(Userbot)
    return clients


async def _resolve_destination(target_channel: str) -> tuple[int, str]:
    configured = {str(channel).strip() for channel in SettingsManager.current().auth_channels}
    if str(target_channel).strip() not in configured:
        raise MediaMoveError("The destination must be one of the configured AUTH media channels.")

    peer = _peer(target_channel)
    last_error: Exception | None = None
    for client in _available_clients():
        try:
            chat = await client.get_chat(peer)
            chat_id = int(chat.id)
            label = (
                getattr(chat, "title", None)
                or getattr(chat, "first_name", None)
                or str(target_channel)
            )
            return chat_id, str(label)
        except Exception as exc:  # Try another connected Telegram account.
            last_error = exc

    if last_error:
        LOGGER.warning("[MediaMove] Destination resolution failed for %s: %s", target_channel, last_error)
    raise MediaMoveError(
        "Could not access the destination channel. Make the bot an admin in that channel."
    )



def _message_media(message: Any) -> Any | None:
    if message is None or bool(getattr(message, "empty", False)):
        return None
    for attr in ("video", "document", "audio", "animation", "voice", "video_note"):
        media = getattr(message, attr, None)
        if media is not None:
            return media
    return None


def _normalized_filename(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    text = text.rsplit("/", 1)[-1]
    return re.sub(r"[^a-z0-9]+", ".", text).strip(".")


def _quality_recovery_hints(quality: dict[str, Any], ref_index: int = 0) -> dict[str, Any]:
    names = {
        _normalized_filename(quality.get(key))
        for key in (
            "source_filename",
            "legacy_source_filename",
            "media_filename",
            "name",
        )
        if quality.get(key)
    }
    names.discard("")

    size_bytes = 0
    parts = sorted(
        quality.get("parts") or [],
        key=lambda part: int(part.get("part_number") or 0),
    )
    if ref_index < len(parts):
        try:
            size_bytes = max(0, int(parts[ref_index].get("size_bytes") or 0))
        except (TypeError, ValueError):
            size_bytes = 0

        # Older split rows do not retain each original part filename. Add the
        # common Telegram split naming forms so an earlier destination copy can
        # still be recovered safely by exact name and size.
        part_number = int(parts[ref_index].get("part_number") or (ref_index + 1))
        base_names = list(names)
        for base in base_names:
            names.add(f"{base}.{part_number:03d}")
            match = re.match(r"^(.*)\.([a-z0-9]{2,5})$", base)
            if match:
                names.add(f"{match.group(1)}.{part_number:03d}.{match.group(2)}")

    display_names = []
    for key in ("source_filename", "legacy_source_filename", "media_filename", "name"):
        value = str(quality.get(key) or "").strip()
        if value and value not in display_names:
            display_names.append(value)
    return {"names": names, "size_bytes": size_bytes, "display_names": display_names}


def _message_matches_hints(message: Any, hints: dict[str, Any]) -> bool:
    media = _message_media(message)
    if media is None:
        return False
    expected_names = set(hints.get("names") or set())
    if not expected_names:
        return False

    actual_names = {
        _normalized_filename(getattr(media, "file_name", None)),
        _normalized_filename(getattr(message, "caption", None)),
    }
    actual_names.discard("")
    if not (actual_names & expected_names):
        # Captions can contain decorative text around the filename. Exact
        # normalized filename containment is still safe because hints include
        # the complete stored source filename, including episode/quality tags.
        caption = _normalized_filename(getattr(message, "caption", None))
        if not caption or not any(name and name in caption for name in expected_names):
            return False

    expected_size = int(hints.get("size_bytes") or 0)
    actual_size = int(getattr(media, "file_size", 0) or 0)
    if expected_size and actual_size and expected_size != actual_size:
        return False
    return True


async def _reupload_message(client: Any, message: Any, target_chat_id: int):
    """Download/re-upload a readable media message when Telegram forbids copy."""
    media = _message_media(message)
    if media is None:
        return None

    with tempfile.TemporaryDirectory(prefix="tg-media-move-") as temp_dir:
        path = await client.download_media(message, file_name=f"{temp_dir}/")
        if not path:
            return None

        common = {
            "chat_id": target_chat_id,
            "caption": getattr(message, "caption", None) or "",
            "caption_entities": getattr(message, "caption_entities", None),
            "disable_notification": True,
        }
        if getattr(message, "video", None) is not None:
            return await client.send_video(
                video=path,
                supports_streaming=True,
                **common,
            )
        if getattr(message, "document", None) is not None:
            return await client.send_document(
                document=path,
                file_name=getattr(media, "file_name", None),
                **common,
            )
        return await client.send_cached_media(
            file_id=getattr(media, "file_id", ""),
            **common,
        )


async def _recover_existing_media(
    *,
    source_ref: tuple[int, int],
    target_chat_id: int,
    hints: dict[str, Any],
    history_cache: dict[int, list[Any]],
) -> tuple[int, int] | None:
    """Find an exact existing copy in AUTH channels and place it in target."""
    if not hints.get("names"):
        return None

    # Prefer the user session for history access, then fall back to bots that
    # can read the configured channels.
    clients = _available_clients()
    if Userbot in clients:
        clients = [Userbot] + [client for client in clients if client is not Userbot]

    candidate_channels: list[int] = [int(target_chat_id)]
    for configured in SettingsManager.current().auth_channels:
        for client in clients:
            try:
                chat = await client.get_chat(_peer(configured))
                chat_id = int(chat.id)
                if chat_id not in candidate_channels:
                    candidate_channels.append(chat_id)
                break
            except Exception:
                continue

    for chat_id in candidate_channels:
        messages = history_cache.get(chat_id)
        if messages is None:
            messages = []
            for client in clients:
                try:
                    async for message in client.get_chat_history(chat_id, limit=2000):
                        if _message_media(message) is not None:
                            messages.append(message)
                    break
                except Exception:
                    messages = []
                    continue
            history_cache[chat_id] = messages

        for message in messages:
            message_ref = (int(getattr(getattr(message, "chat", None), "id", chat_id)), int(getattr(message, "id", 0) or 0))
            if message_ref == source_ref or message_ref[1] <= 0:
                continue
            if not _message_matches_hints(message, hints):
                continue
            if int(message_ref[0]) == int(target_chat_id):
                return message_ref
            try:
                copied = await _copy_one(message_ref[0], message_ref[1], target_chat_id)
            except MediaMoveError:
                continue
            copied_id = int(getattr(copied, "id", 0) or 0)
            if copied_id > 0:
                return (int(target_chat_id), copied_id)
    return None


async def _copy_one(source_chat_id: int, message_id: int, target_chat_id: int):
    """Copy one post serially, retrying connected clients and re-upload fallback."""
    global _COPY_CLIENT_CURSOR, _LAST_FLOOD_LOG_AT

    async with _COPY_LOCK:
        clients = _available_clients()
        if not clients:
            raise MediaMoveError("No Telegram client is connected.")

        offset = _COPY_CLIENT_CURSOR % len(clients)
        ordered = clients[offset:] + clients[:offset]
        _COPY_CLIENT_CURSOR = (_COPY_CLIENT_CURSOR + 1) % len(clients)

        last_error: Exception | None = None
        readable_candidates: list[tuple[Any, Any]] = []
        client_count = len(ordered)

        for attempt in range(2):
            waits: list[int] = []
            attempted = 0
            readable_candidates.clear()
            for client in ordered:
                if getattr(client, "is_connected", None) is False:
                    continue
                attempted += 1
                try:
                    source_message = await client.get_messages(source_chat_id, message_id)
                    if _message_media(source_message) is None:
                        last_error = RuntimeError("source message is empty or has no media")
                        continue
                    readable_candidates.append((client, source_message))
                    copied = await source_message.copy(
                        chat_id=target_chat_id,
                        disable_notification=True,
                    )
                    copied_id = int(getattr(copied, "id", 0) or 0)
                    if copied is None or copied_id <= 0:
                        last_error = RuntimeError("Telegram returned no copied message")
                        continue

                    copied_chat_id = int(
                        getattr(getattr(copied, "chat", None), "id", target_chat_id)
                    )
                    mark_mover_message(copied_chat_id, copied_id)
                    await asyncio.sleep(_COPY_DELAY_SECONDS)
                    return copied
                except FloodWait as exc:
                    last_error = exc
                    waits.append(max(1, int(getattr(exc, "value", 1) or 1)))
                except Exception as exc:
                    last_error = exc

            if attempted == 0:
                await asyncio.sleep(1)
                ordered = _available_clients()
                client_count = len(ordered)
                if ordered:
                    continue

            if waits and attempt == 0:
                wait_seconds = min(waits)
                now = monotonic()
                if now - _LAST_FLOOD_LOG_AT >= _FLOOD_LOG_INTERVAL_SECONDS:
                    LOGGER.warning(
                        "[MediaMove] Telegram rate limit detected; waiting %ss before retrying.",
                        wait_seconds,
                    )
                    _LAST_FLOOD_LOG_AT = now
                await asyncio.sleep(wait_seconds + 1)
                ordered = _available_clients() or ordered
                continue
            break

        # copy_message/send_cached_media cannot handle protected media in some
        # channels. Re-upload only once, preferring the user session, and keep
        # this fallback quiet unless it ultimately fails.
        if readable_candidates:
            readable_candidates.sort(key=lambda item: 0 if item[0] is Userbot else 1)
            for client, source_message in readable_candidates:
                try:
                    copied = await _reupload_message(client, source_message, target_chat_id)
                    copied_id = int(getattr(copied, "id", 0) or 0)
                    if copied is None or copied_id <= 0:
                        continue
                    copied_chat_id = int(
                        getattr(getattr(copied, "chat", None), "id", target_chat_id)
                    )
                    mark_mover_message(copied_chat_id, copied_id)
                    await asyncio.sleep(_COPY_DELAY_SECONDS)
                    return copied
                except FloodWait as exc:
                    wait_seconds = max(1, int(getattr(exc, "value", 1) or 1))
                    await asyncio.sleep(wait_seconds + 1)
                except Exception as exc:
                    last_error = exc

        detail = str(last_error or "source message is unavailable")
        raise MediaMoveError(
            f"Could not copy Telegram message {message_id} after trying "
            f"{client_count} connected client(s): {detail}."
        )


async def _delete_refs(refs: Iterable[tuple[int, int]]) -> list[tuple[int, int]]:
    grouped: dict[int, set[int]] = defaultdict(set)
    for chat_id, message_id in refs:
        grouped[int(chat_id)].add(int(message_id))

    failed: list[tuple[int, int]] = []
    for chat_id, message_ids in grouped.items():
        remaining = await delete_messages_batch(chat_id, sorted(message_ids), quiet=True)
        failed.extend((chat_id, message_id) for message_id in (remaining or []))
    return failed


async def move_indexed_quality(
    database,
    *,
    tmdb_id: int,
    db_index: int,
    media_type: str,
    quality_id: str,
    target_channel: str,
    season: int | None = None,
    episode: int | None = None,
) -> dict[str, Any]:
    """Move one movie/episode quality and return a UI-friendly result."""

    quality = await database.get_media_quality(
        media_type=media_type,
        tmdb_id=tmdb_id,
        db_index=db_index,
        quality_id=quality_id,
        season_number=season,
        episode_number=episode,
    )
    if not quality:
        raise MediaMoveError("The selected indexed file no longer exists. Refresh the page and try again.")

    quality_for_refs = deepcopy(quality)
    if quality_for_refs.get("parts"):
        quality_for_refs["parts"] = sorted(
            quality_for_refs["parts"],
            key=lambda part: int(part.get("part_number") or 0),
        )
    source_refs = await database._quality_message_refs(quality_for_refs)
    if not source_refs:
        raise MediaMoveError("The Telegram source references for this file could not be decoded.")

    target_chat_id, target_name = await _resolve_destination(target_channel)
    if any(int(source_chat_id) == target_chat_id for source_chat_id, _ in source_refs):
        raise MediaMoveError("This file is already stored in the selected destination channel.")

    copied_refs: list[tuple[int, int]] = []
    async with suppress_move_destination(target_chat_id):
        try:
            for source_chat_id, message_id in source_refs:
                copied = await _copy_one(source_chat_id, message_id, target_chat_id)
                copied_chat_id = int(getattr(getattr(copied, "chat", None), "id", target_chat_id))
                copied_message_id = int(getattr(copied, "id", 0) or 0)
                if copied_message_id <= 0:
                    raise MediaMoveError("Telegram copied a file but did not return its new message ID.")
                copied_refs.append((copied_chat_id, copied_message_id))

            replacement = deepcopy(quality)
            parts = replacement.get("parts") or []
            if parts:
                if len(parts) != len(copied_refs):
                    raise MediaMoveError("The split-file part count changed during the move.")
                ordered_parts = sorted(parts, key=lambda part: int(part.get("part_number") or 0))
                for part, (new_chat_id, new_message_id) in zip(ordered_parts, copied_refs):
                    part["chat_id"] = to_stored_chat_id(new_chat_id)
                    part["msg_id"] = new_message_id
                replacement["parts"] = ordered_parts
                replacement["id"], replacement["size"] = await database._build_part_id_and_size(
                    ordered_parts,
                    split_kind=replacement.get("split_kind") or "raw",
                    media_filename=replacement.get("media_filename") or replacement.get("name"),
                )
            elif len(copied_refs) > 1:
                # Compatibility for older virtual split records whose encoded ID
                # contains multiple parts but whose Mongo row predates the `parts`
                # field. Preserve the legacy payload shape while replacing refs.
                try:
                    legacy_payload = await decode_string(quality_id)
                except Exception:
                    legacy_payload = {}
                payload = dict(legacy_payload) if isinstance(legacy_payload, dict) else {}
                payload["parts"] = [
                    {"chat_id": to_stored_chat_id(new_chat_id), "msg_id": new_message_id}
                    for new_chat_id, new_message_id in copied_refs
                ]
                replacement["id"] = await encode_string(payload)
            else:
                new_chat_id, new_message_id = copied_refs[0]
                replacement["id"] = await encode_string(
                    {"chat_id": to_stored_chat_id(new_chat_id), "msg_id": new_message_id}
                )

            saved = await database.replace_media_quality_source(
                media_type=media_type,
                tmdb_id=tmdb_id,
                db_index=db_index,
                old_quality_id=quality_id,
                replacement_quality=replacement,
                season_number=season,
                episode_number=episode,
            )
            if not saved:
                raise MediaMoveError(
                    "The new Telegram copy was created, but the database record could not be updated."
                )
        except Exception:
            if copied_refs:
                cleanup_failed = await _delete_refs(copied_refs)
                if cleanup_failed:
                    LOGGER.error(
                        "[MediaMove] Could not roll back %s copied destination message(s): %s",
                        len(cleanup_failed),
                        cleanup_failed,
                    )
            raise
    try:
        deletion_failed = await _delete_refs(source_refs)
    except Exception as exc:
        LOGGER.exception("[MediaMove] New source saved but old-source deletion failed: %s", exc)
        deletion_failed = list(source_refs)
    moved_count = len(copied_refs)
    LOGGER.info(
        "[MediaMove] Moved %s Telegram message(s) for %s to %s (%s); old-delete failures=%s",
        moved_count,
        quality_id,
        target_name,
        target_chat_id,
        len(deletion_failed),
    )

    if deletion_failed:
        return {
            "message": (
                f"Moved to {target_name}, but {len(deletion_failed)} old Telegram "
                "message(s) could not be deleted. Check channel admin permissions."
            ),
            "moved": True,
            "old_files_removed": False,
            "parts_moved": moved_count,
            "target_channel": target_name,
        }

    return {
        "message": f"Moved to {target_name} and removed the old Telegram file(s).",
        "moved": True,
        "old_files_removed": True,
        "parts_moved": moved_count,
        "target_channel": target_name,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Whole-title moves (all movie qualities or every series episode/quality)
# ─────────────────────────────────────────────────────────────────────────────

FullMoveProgress = Callable[[dict[str, Any]], Awaitable[None] | None]
_FULL_MOVE_JOBS: dict[str, dict[str, Any]] = {}
_FULL_MOVE_ACTIVE: dict[str, str] = {}


def _public_job(job: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in job.items() if key not in {"task", "active_key"}}


async def _emit_progress(callback: FullMoveProgress | None, **payload: Any) -> None:
    if callback is None:
        return
    result = callback(payload)
    if asyncio.iscoroutine(result):
        await result


async def _replacement_with_refs(database, quality: dict[str, Any], refs: list[tuple[int, int]]) -> dict[str, Any]:
    replacement = deepcopy(quality)
    parts = replacement.get("parts") or []
    if parts:
        ordered_parts = sorted(parts, key=lambda part: int(part.get("part_number") or 0))
        if len(ordered_parts) != len(refs):
            raise MediaMoveError("A split-file part count changed while preparing the full-title move.")
        for part, (chat_id, message_id) in zip(ordered_parts, refs):
            part["chat_id"] = to_stored_chat_id(chat_id)
            part["msg_id"] = int(message_id)
        replacement["parts"] = ordered_parts
        replacement["id"], replacement["size"] = await database._build_part_id_and_size(
            ordered_parts,
            split_kind=replacement.get("split_kind") or "raw",
            media_filename=replacement.get("media_filename") or replacement.get("name"),
        )
        return replacement

    if len(refs) > 1:
        try:
            legacy_payload = await decode_string(quality.get("id"))
        except Exception:
            legacy_payload = {}
        payload = dict(legacy_payload) if isinstance(legacy_payload, dict) else {}
        payload["parts"] = [
            {"chat_id": to_stored_chat_id(chat_id), "msg_id": int(message_id)}
            for chat_id, message_id in refs
        ]
        replacement["id"] = await encode_string(payload)
        return replacement

    if len(refs) != 1:
        raise MediaMoveError("An indexed file has no usable Telegram source reference.")
    chat_id, message_id = refs[0]
    replacement["id"] = await encode_string(
        {"chat_id": to_stored_chat_id(chat_id), "msg_id": int(message_id)}
    )
    return replacement


async def _full_title_source_refs(
    database, *, tmdb_id: int, db_index: int, media_type: str
) -> list[tuple[int, int]]:
    """Return the unique Telegram sources currently indexed for one title."""
    normalized_type = "tv" if str(media_type or "").lower() in {"tv", "series"} else "movie"
    document = await database.get_document(normalized_type, int(tmdb_id), int(db_index))
    if not document:
        raise MediaMoveError("This media record no longer exists. Refresh the page and try again.")

    qualities: list[dict[str, Any]] = []
    if normalized_type == "movie":
        qualities.extend(document.get("telegram") or [])
    else:
        for season in document.get("seasons") or []:
            for episode in season.get("episodes") or []:
                qualities.extend(episode.get("telegram") or [])

    refs: list[tuple[int, int]] = []
    seen: set[tuple[int, int]] = set()
    for quality in qualities:
        prepared = deepcopy(quality)
        if prepared.get("parts"):
            prepared["parts"] = sorted(
                prepared["parts"], key=lambda part: int(part.get("part_number") or 0)
            )
        for chat_id, message_id in await database._quality_message_refs(prepared):
            ref = (int(chat_id), int(message_id))
            if ref not in seen:
                seen.add(ref)
                refs.append(ref)
    if not refs:
        raise MediaMoveError("No indexed Telegram files were found for this title.")
    return refs


async def list_full_media_move_channels(
    database, *, tmdb_id: int, db_index: int, media_type: str
) -> list[dict[str, str]]:
    """Resolve configured destinations and omit a channel already holding all files."""
    refs = await _full_title_source_refs(
        database, tmdb_id=tmdb_id, db_index=db_index, media_type=media_type
    )
    source_chats = {chat_id for chat_id, _ in refs}
    result: list[dict[str, str]] = []
    for configured in SettingsManager.current().auth_channels:
        try:
            chat_id, name = await _resolve_destination(str(configured))
        except MediaMoveError as exc:
            LOGGER.warning("[MediaMove] Skipping unavailable destination %s: %s", configured, exc)
            continue
        if source_chats == {int(chat_id)}:
            continue
        result.append({"id": str(configured), "name": str(name)})
    return result


async def preflight_full_media_move(
    database, *, tmdb_id: int, db_index: int, media_type: str, target_channel: str
) -> None:
    """Reject a no-op destination before a background job is created."""
    refs = await _full_title_source_refs(
        database, tmdb_id=tmdb_id, db_index=db_index, media_type=media_type
    )
    target_chat_id, target_name = await _resolve_destination(target_channel)
    if all(int(chat_id) == int(target_chat_id) for chat_id, _ in refs):
        raise MediaMoveError(f"All files for this title are already stored in {target_name}.")


async def move_full_media_title(
    database,
    *,
    tmdb_id: int,
    db_index: int,
    media_type: str,
    target_channel: str,
    progress_callback: FullMoveProgress | None = None,
) -> dict[str, Any]:
    """Move every indexed stream belonging to one movie or full TV series.

    The operation is title-level and copy-first: all required Telegram messages
    are copied, one MongoDB title document is updated, and only then are old
    posts removed. Any failure before the database update rolls back every new
    destination copy.
    """
    normalized_type = "tv" if str(media_type or "").lower() in {"tv", "series"} else "movie"
    document = await database.get_document(normalized_type, int(tmdb_id), int(db_index))
    if not document:
        raise MediaMoveError("This media record no longer exists. Refresh the page and try again.")

    target_chat_id, target_name = await _resolve_destination(target_channel)
    moved_document = deepcopy(document)
    entries: list[dict[str, Any]] = []

    if normalized_type == "movie":
        qualities = moved_document.get("telegram") or []
        for index, quality in enumerate(qualities):
            prepared = deepcopy(quality)
            if prepared.get("parts"):
                prepared["parts"] = sorted(
                    prepared["parts"], key=lambda part: int(part.get("part_number") or 0)
                )
            refs = await database._quality_message_refs(prepared)
            if refs:
                entries.append({"container": qualities, "index": index, "quality": prepared, "refs": refs})
    else:
        for season in moved_document.get("seasons") or []:
            for episode in season.get("episodes") or []:
                qualities = episode.get("telegram") or []
                for index, quality in enumerate(qualities):
                    prepared = deepcopy(quality)
                    if prepared.get("parts"):
                        prepared["parts"] = sorted(
                            prepared["parts"], key=lambda part: int(part.get("part_number") or 0)
                        )
                    refs = await database._quality_message_refs(prepared)
                    if refs:
                        entries.append({"container": qualities, "index": index, "quality": prepared, "refs": refs})

    if not entries:
        raise MediaMoveError("No indexed Telegram files were found for this title.")

    unique_refs: list[tuple[int, int]] = []
    seen_refs: set[tuple[int, int]] = set()
    for entry in entries:
        for ref in entry["refs"]:
            normalized_ref = (int(ref[0]), int(ref[1]))
            if normalized_ref not in seen_refs:
                seen_refs.add(normalized_ref)
                unique_refs.append(normalized_ref)

    ref_hints: dict[tuple[int, int], dict[str, Any]] = {}
    for entry in entries:
        entry_refs = [(int(chat_id), int(message_id)) for chat_id, message_id in entry["refs"]]
        for ref_index, ref in enumerate(entry_refs):
            incoming = _quality_recovery_hints(entry["quality"], ref_index)
            current = ref_hints.setdefault(
                ref, {"names": set(), "size_bytes": 0, "display_names": []}
            )
            current["names"].update(incoming.get("names") or set())
            for display_name in incoming.get("display_names") or []:
                if display_name not in current["display_names"]:
                    current["display_names"].append(display_name)
            if not current.get("size_bytes") and incoming.get("size_bytes"):
                current["size_bytes"] = int(incoming["size_bytes"])

    refs_to_copy = [ref for ref in unique_refs if int(ref[0]) != int(target_chat_id)]
    if not refs_to_copy:
        raise MediaMoveError(f"All files for this title are already stored in {target_name}.")

    await _emit_progress(
        progress_callback,
        stage="copying",
        message=f"Preparing {len(entries)} indexed stream(s)…",
        total_messages=len(refs_to_copy),
        copied_messages=0,
        files_total=len(entries),
        files_moved=0,
        progress=2,
        target_channel=target_name,
    )

    LOGGER.info(
        "[MediaMove] Starting full %s %s to %s: messages=%s delay=%.1fs",
        normalized_type,
        tmdb_id,
        target_name,
        len(refs_to_copy),
        _COPY_DELAY_SECONDS,
    )

    ref_map: dict[tuple[int, int], tuple[int, int]] = {
        ref: ref for ref in unique_refs if int(ref[0]) == int(target_chat_id)
    }
    copied_refs: list[tuple[int, int]] = []
    moved_source_refs: list[tuple[int, int]] = []
    failed_refs: list[tuple[int, int]] = []
    recovered_existing_refs: list[tuple[int, int]] = []
    history_cache: dict[int, list[Any]] = {}
    progress_log_step = max(25, max(1, len(refs_to_copy) // 4))
    async with suppress_move_destination(target_chat_id):
        try:
            for position, source_ref in enumerate(refs_to_copy, start=1):
                try:
                    copied = await _copy_one(source_ref[0], source_ref[1], target_chat_id)
                except MediaMoveError:
                    recovered = await _recover_existing_media(
                        source_ref=source_ref,
                        target_chat_id=target_chat_id,
                        hints=ref_hints.get(source_ref) or {},
                        history_cache=history_cache,
                    )
                    if recovered is not None:
                        ref_map[source_ref] = recovered
                        recovered_existing_refs.append(recovered)
                        moved_source_refs.append(source_ref)
                    else:
                        # Keep this source reference unchanged. A later run will
                        # see only the remaining old sources and resume from there.
                        ref_map[source_ref] = source_ref
                        failed_refs.append(source_ref)
                else:
                    new_ref = (
                        int(getattr(getattr(copied, "chat", None), "id", target_chat_id)),
                        int(getattr(copied, "id", 0) or 0),
                    )
                    if new_ref[1] <= 0:
                        ref_map[source_ref] = source_ref
                        failed_refs.append(source_ref)
                    else:
                        ref_map[source_ref] = new_ref
                        copied_refs.append(new_ref)
                        moved_source_refs.append(source_ref)

                if position % progress_log_step == 0 and position < len(refs_to_copy):
                    LOGGER.info(
                        "[MediaMove] Full-title progress: checked=%s/%s moved=%s skipped=%s",
                        position,
                        len(refs_to_copy),
                        len(copied_refs) + len(recovered_existing_refs),
                        len(failed_refs),
                    )

                await _emit_progress(
                    progress_callback,
                    stage="copying",
                    message=(
                        f"Processed {position} of {len(refs_to_copy)} file(s)"
                        + (f" · {len(failed_refs)} waiting for retry" if failed_refs else "")
                    ),
                    total_messages=len(refs_to_copy),
                    copied_messages=len(copied_refs) + len(recovered_existing_refs),
                    skipped_messages=len(failed_refs),
                    files_total=len(entries),
                    files_moved=0,
                    progress=max(3, min(84, round(position / len(refs_to_copy) * 84))),
                    target_channel=target_name,
                )

            if not copied_refs and not recovered_existing_refs:
                missing_names: list[str] = []
                for failed_ref in failed_refs:
                    for name in (ref_hints.get(failed_ref) or {}).get("display_names") or []:
                        if name not in missing_names:
                            missing_names.append(name)
                            break
                missing_text = ""
                if missing_names:
                    missing_text = " Missing: " + "; ".join(missing_names[:4]) + "."
                raise MediaMoveError(
                    f"Could not recover the remaining {len(failed_refs)} source file(s)."
                    f"{missing_text} The original Telegram posts appear deleted or inaccessible "
                    "in every configured AUTH channel. Re-upload those files to any AUTH channel, "
                    "then run Move again."
                )

            changed_entries = 0
            for entry in entries:
                source_refs = [(int(chat_id), int(message_id)) for chat_id, message_id in entry["refs"]]
                replacement_refs = [ref_map[ref] for ref in source_refs]
                if replacement_refs != source_refs:
                    changed_entries += 1
                entry["container"][entry["index"]] = await _replacement_with_refs(
                    database, entry["quality"], replacement_refs
                )

            await _emit_progress(
                progress_callback,
                stage="saving",
                message="Saving the full title to the media index…",
                total_messages=len(refs_to_copy),
                copied_messages=len(copied_refs) + len(recovered_existing_refs),
                skipped_messages=len(failed_refs),
                files_total=len(entries),
                files_moved=changed_entries,
                progress=90,
                target_channel=target_name,
            )

            update_payload = {"updated_on": datetime.utcnow()}
            if normalized_type == "movie":
                update_payload["telegram"] = moved_document.get("telegram") or []
            else:
                update_payload["seasons"] = moved_document.get("seasons") or []

            saved = await database.update_document(
                normalized_type, int(tmdb_id), int(db_index), update_payload
            )
            if not saved:
                raise MediaMoveError(
                    "All destination copies were created, but the full media record could not be updated."
                )
        except Exception:
            if copied_refs:
                cleanup_failed = await _delete_refs(copied_refs)
                if cleanup_failed:
                    LOGGER.error(
                        "[MediaMove] Full-title rollback left %s destination message(s): %s",
                        len(cleanup_failed), cleanup_failed,
                    )
            raise

    await _emit_progress(
        progress_callback,
        stage="cleanup",
        message="Removing old Telegram posts for successfully moved files…",
        total_messages=len(refs_to_copy),
        copied_messages=len(copied_refs) + len(recovered_existing_refs),
        skipped_messages=len(failed_refs),
        files_total=len(entries),
        files_moved=changed_entries,
        progress=95,
        target_channel=target_name,
    )
    try:
        deletion_failed = await _delete_refs(moved_source_refs)
    except Exception as exc:
        LOGGER.error("[MediaMove] Old-source cleanup failed after the index was saved: %s", exc)
        deletion_failed = list(moved_source_refs)

    media_label = "series" if normalized_type == "tv" else "movie"
    warning_parts: list[str] = []
    if failed_refs:
        warning_parts.append(
            f"{len(failed_refs)} unavailable source file(s) were left unchanged for retry"
        )
    if deletion_failed:
        warning_parts.append(
            f"{len(deletion_failed)} old Telegram post(s) could not be deleted"
        )
    if warning_parts:
        message = (
            f"Moved {len(copied_refs) + len(recovered_existing_refs)} file(s) from the full {media_label} to {target_name}; "
            + "; ".join(warning_parts)
            + ". Run Move again to continue the remaining files."
        )
    else:
        message = f"Moved the full {media_label} to {target_name}."

    result = {
        "message": message,
        "moved": True,
        "old_files_removed": not deletion_failed and not failed_refs,
        "target_channel": target_name,
        "files_total": len(entries),
        "files_moved": changed_entries,
        "messages_moved": len(copied_refs) + len(recovered_existing_refs),
        "messages_skipped": len(failed_refs),
        "old_delete_failures": len(deletion_failed),
    }
    LOGGER.info(
        "[MediaMove] Full %s %s finished: destination=%s moved=%s skipped=%s delete_failures=%s",
        normalized_type,
        tmdb_id,
        target_name,
        len(copied_refs) + len(recovered_existing_refs),
        len(failed_refs),
        len(deletion_failed),
    )
    return result


async def start_full_media_move(
    database,
    *,
    tmdb_id: int,
    db_index: int,
    media_type: str,
    target_channel: str,
) -> dict[str, Any]:
    normalized_type = "tv" if str(media_type or "").lower() in {"tv", "series"} else "movie"
    await preflight_full_media_move(
        database,
        tmdb_id=int(tmdb_id),
        db_index=int(db_index),
        media_type=normalized_type,
        target_channel=str(target_channel),
    )
    active_key = f"{int(db_index)}:{normalized_type}:{int(tmdb_id)}"
    existing_id = _FULL_MOVE_ACTIVE.get(active_key)
    if existing_id:
        existing = _FULL_MOVE_JOBS.get(existing_id)
        if existing and existing.get("status") in {"queued", "running"}:
            raise MediaMoveError("A full-title move is already running for this media record.")

    job_id = uuid4().hex
    job = {
        "job_id": job_id,
        "status": "queued",
        "stage": "queued",
        "message": "Move queued…",
        "progress": 0,
        "copied_messages": 0,
        "skipped_messages": 0,
        "total_messages": 0,
        "files_moved": 0,
        "files_total": 0,
        "target_channel": "",
        "old_files_removed": None,
        "error": None,
        "active_key": active_key,
    }
    _FULL_MOVE_JOBS[job_id] = job
    _FULL_MOVE_ACTIVE[active_key] = job_id

    async def update_job(payload: dict[str, Any]) -> None:
        job.update(payload)
        job["status"] = "running"

    async def runner() -> None:
        try:
            job.update({"status": "running", "stage": "starting", "message": "Starting full-title move…", "progress": 1})
            result = await move_full_media_title(
                database,
                tmdb_id=int(tmdb_id),
                db_index=int(db_index),
                media_type=normalized_type,
                target_channel=str(target_channel),
                progress_callback=update_job,
            )
            job.update(result)
            job.update({"status": "completed", "stage": "completed", "progress": 100})
        except MediaMoveError as exc:
            LOGGER.warning("[MediaMove] Full-title job %s stopped: %s", job_id, exc)
            job.update({
                "status": "failed",
                "stage": "failed",
                "message": str(exc),
                "error": str(exc),
            })
        except Exception as exc:
            LOGGER.exception("[MediaMove] Full-title job %s failed: %s", job_id, exc)
            job.update({
                "status": "failed",
                "stage": "failed",
                "message": "The full-title move failed unexpectedly. Check the server log.",
                "error": "The full-title move failed unexpectedly. Check the server log.",
            })
        finally:
            _FULL_MOVE_ACTIVE.pop(active_key, None)

    job["task"] = asyncio.create_task(runner())
    return _public_job(job)


def get_full_media_move_status(job_id: str) -> dict[str, Any]:
    job = _FULL_MOVE_JOBS.get(str(job_id or ""))
    if not job:
        raise MediaMoveError("This move job was not found or the server restarted.")
    return _public_job(job)
