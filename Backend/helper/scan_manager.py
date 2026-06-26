from __future__ import annotations

import asyncio
import time
from typing import Any, Dict, List, Optional

from pyrogram.errors import FloodWait, ChannelPrivate, ChatAdminRequired

from Backend.logger import LOGGER
from Backend.helper.encrypt import encode_string, decode_string
from Backend.helper.metadata import metadata
from Backend.helper.pyro import clean_filename, get_readable_file_size, remove_urls
from Backend.helper.subtitle_service import index_subtitle, relink_unmatched_subtitles
from Backend.helper.subtitle_constants import is_subtitle_file
from Backend.helper.split_files import detect_split_file, detect_split_upload, strip_part_suffix, find_split_source, split_metadata_fields


# ─────────────────────────────────────────────────────────────────────────────
# Tunables — kept conservative so we never trip Telegram's flood limits.
# ─────────────────────────────────────────────────────────────────────────────
SCAN_BATCH_SIZE = 200          # get_messages accepts up to 200 ids per call
SCAN_MAX_EMPTY_BATCHES = 10    # stop after this many consecutive empty batches
SCAN_MAX_ID_CAP = 1_000_000    # hard ceiling to avoid runaway loops
# Metadata lookups are network-bound. Four workers give a major rescan speed-up
# on small HF instances while staying well below the shared API limit of 12.
SCAN_METADATA_CONCURRENCY = 4
SCAN_BATCH_DELAY = 0.05        # tiny pause between Telegram fetch batches
SCAN_PERSIST_EVERY = 1         # persist state every N batches

DBCHECK_CONCURRENCY = 5        # concurrent get_messages during integrity check
DBCHECK_BATCH_DELAY = 0.3      # seconds between concurrent groups
DBCHECK_PAGE_SIZE = 100        # mongo pagination size

_STATE_COLLECTION = "scan_state"
_SCAN_DOC_ID = "scan"


def _now() -> float:
    return time.time()


def _fmt_elapsed(seconds: float) -> str:
    s = int(seconds)
    m, s = divmod(s, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}h {m}m {s}s"
    if m:
        return f"{m}m {s}s"
    return f"{s}s"


class _OrderedBatchCommit:
    """Keep database commits in Telegram message order.

    A scan may resolve metadata for several files concurrently, but Replace Mode
    must still see uploads in their original channel order.  Each worker waits
    for its turn only at commit time, so slow API lookups overlap safely.
    """

    def __init__(self) -> None:
        self._next = 0
        self._condition = asyncio.Condition()

    async def wait_turn(self, slot: int) -> None:
        async with self._condition:
            await self._condition.wait_for(lambda: self._next == slot)

    async def finish(self, slot: int) -> None:
        async with self._condition:
            if self._next != slot:
                return
            self._next += 1
            self._condition.notify_all()


# ═════════════════════════════════════════════════════════════════════════════
# ═════════════════════════════════════════════════════════════════════════════
#  ScanManager — one channel scanner with media/subtitle scope selection
# ═════════════════════════════════════════════════════════════════════════════
class ScanManager:
    """Resumable channel scanner for media, subtitles, or both.

    Each scope keeps its own cursor. A subtitle-only pass can therefore start
    from the first channel message even after a media scan has already reached
    the newest post.
    """

    VALID_SCOPES = {"media", "subtitles", "all"}

    def __init__(self) -> None:
        self._db = None
        self._task: Optional[asyncio.Task] = None
        self._cancel = False
        self._lock = asyncio.Lock()
        self.state: Dict[str, Any] = self._blank_state()

    @staticmethod
    def _blank_counters() -> Dict[str, int]:
        return {
            "total_found": 0,
            "processed": 0,
            "indexed": 0,
            "skipped_dup": 0,
            "skipped_meta": 0,
            "skipped_nonvid": 0,
            "subtitles_found": 0,
            "subtitles_indexed": 0,
            "subtitles_matched": 0,
            "subtitles_unmatched": 0,
            "subtitles_relinked": 0,
            "subtitles_replaced": 0,
            "errors": 0,
        }

    @classmethod
    def _blank_state(cls) -> Dict[str, Any]:
        return {
            "status": "idle",            # idle|running|paused|completed|cancelled|error
            # scanning|finalizing|idle.  The UI keeps the bar below 100% while
            # final subtitle linking and counter reconciliation are still running.
            "phase": "idle",
            "mode": "scan",              # scan|rescan
            "content_scope": "all",      # media|subtitles|all
            "selected_channels": [],
            "pending": [],
            "current_channel": None,
            "current_channel_name": "",
            "current_id": 0,
            "start_message_id": 0,
            "latest_message_id": 0,
            # True only when a real user session returned the Telegram history
            # tail. Bot accounts cannot call messages.GetHistory, so their
            # internal probe ceiling must never be shown as a channel end ID.
            "tail_is_exact": False,
            # Internal scan ceiling. With a bot-only client this is a probe
            # window, not the actual Telegram channel tail.
            "target_message_id": 0,
            "summary": "",
            # Separate cursors ensure one mode never skips another mode's files.
            "cursors": {"media": {}, "subtitles": {}, "all": {}},
            "counters": cls._blank_counters(),
            # Stream IDs of subtitle rows touched during this scan.  These let
            # the completed scan card report their final match state instead of
            # retaining a temporary "unmatched" result from before media was indexed.
            "subtitle_scanned_stream_ids": [],
            "started_at": 0.0,
            "updated_at": 0.0,
            "finished_at": 0.0,
            "error": None,
        }

    @classmethod
    def _normalise_scope(cls, value: str | None) -> str:
        value = str(value or "all").strip().lower()
        aliases = {"video": "media", "videos": "media", "subtitle": "subtitles", "both": "all"}
        value = aliases.get(value, value)
        return value if value in cls.VALID_SCOPES else "all"

    def _cursor_map(self) -> Dict[str, int]:
        cursors = self.state.setdefault("cursors", {})
        scope = self._normalise_scope(self.state.get("content_scope"))
        scope_map = cursors.setdefault(scope, {})
        return scope_map

    def bind_db(self, db) -> None:
        self._db = db

    async def load(self, db) -> None:
        """Restore state and migrate old one-cursor scanner state safely."""
        self._db = db
        try:
            doc = await db.dbs["tracking"][_STATE_COLLECTION].find_one({"_id": _SCAN_DOC_ID})
        except Exception as exc:
            LOGGER.error(f"[ScanManager] load failed: {exc}")
            doc = None

        if not doc:
            self.state = self._blank_state()
            return

        doc.pop("_id", None)
        restored = self._blank_state()
        restored.update(doc)

        raw_cursors = doc.get("cursors") or {}
        # v3.3.1 stored {channel: cursor}. It scanned all file types, so retain
        # that cursor for all/media while allowing a fresh subtitle-only pass.
        if raw_cursors and all(not isinstance(value, dict) for value in raw_cursors.values()):
            flat = {str(channel): int(cursor) for channel, cursor in raw_cursors.items()}
            restored["cursors"] = {"media": dict(flat), "subtitles": {}, "all": dict(flat)}
        else:
            cursor_groups = {"media": {}, "subtitles": {}, "all": {}}
            for scope in cursor_groups:
                cursor_groups[scope] = {
                    str(channel): int(cursor)
                    for channel, cursor in (raw_cursors.get(scope) or {}).items()
                }
            restored["cursors"] = cursor_groups

        counters = self._blank_counters()
        counters.update(doc.get("counters") or {})
        restored["counters"] = counters
        restored["content_scope"] = self._normalise_scope(doc.get("content_scope"))
        restored["subtitle_scanned_stream_ids"] = list(dict.fromkeys(
            str(stream_id).strip()
            for stream_id in (doc.get("subtitle_scanned_stream_ids") or [])
            if str(stream_id).strip()
        ))
        if restored["status"] == "running":
            restored["status"] = "paused"
        self.state = restored
        if self.state["status"] == "paused":
            LOGGER.info("[ScanManager] Interrupted scan restored as paused (resumable).")
        await self._persist()

    async def _persist(self) -> None:
        if self._db is None:
            return
        self.state["updated_at"] = _now()
        try:
            document = dict(self.state)
            document["_id"] = _SCAN_DOC_ID
            await self._db.dbs["tracking"][_STATE_COLLECTION].update_one(
                {"_id": _SCAN_DOC_ID}, {"$set": document}, upsert=True
            )
        except Exception as exc:
            LOGGER.error(f"[ScanManager] persist failed: {exc}")

    def get_status(self) -> Dict[str, Any]:
        state = self.state
        elapsed = 0.0
        if state["started_at"]:
            elapsed = max(0.0, (state["finished_at"] or _now()) - state["started_at"])
        return {
            "status": state["status"],
            "phase": str(state.get("phase") or "idle"),
            "mode": state["mode"],
            "content_scope": self._normalise_scope(state.get("content_scope")),
            "is_running": state["status"] == "running",
            "resumable": state["status"] in ("paused", "cancelled") and bool(state["pending"]),
            "selected_channels": list(state["selected_channels"]),
            "pending": list(state["pending"]),
            "current_channel": state["current_channel"],
            "current_channel_name": state["current_channel_name"],
            "current_id": state["current_id"],
            "start_message_id": int(state.get("start_message_id") or 0),
            "latest_message_id": int(state.get("latest_message_id") or 0),
            "tail_is_exact": bool(state.get("tail_is_exact")),
            "target_message_id": int(state.get("target_message_id") or 0),
            "summary": str(state.get("summary") or ""),
            "counters": dict(state["counters"]),
            "elapsed": _fmt_elapsed(elapsed),
            "elapsed_seconds": int(elapsed),
            "error": state["error"],
        }

    def _track_scanned_subtitle(self, record: Dict[str, Any]) -> None:
        """Remember a scan-run subtitle so final counters can use its real status."""
        stream_id = str(record.get("stream_id") or "").strip()
        if not stream_id:
            return
        tracked = self.state.setdefault("subtitle_scanned_stream_ids", [])
        if stream_id not in tracked:
            tracked.append(stream_id)

    async def _reconcile_subtitle_counters(self) -> None:
        """Replace temporary subtitle match counters with final persisted statuses.

        A subtitle can be indexed before its video appears later in the same
        channel.  It is briefly unmatched, then linked after that video is
        indexed.  The scan card must show the final state, not that transient
        first pass.
        """
        stream_ids = self.state.get("subtitle_scanned_stream_ids") or []
        if not stream_ids or self._db is None:
            return
        try:
            status_counts = await self._db.get_subtitle_status_counts(stream_ids)
        except Exception as exc:
            LOGGER.warning("[ScanManager] Could not reconcile subtitle counters: %s", exc)
            return

        matched = int(status_counts.get("matched") or 0)
        unmatched = int(status_counts.get("unmatched") or 0)
        counters = self.state["counters"]
        counters["subtitles_matched"] = matched
        counters["subtitles_unmatched"] = unmatched
        LOGGER.info(
            "[ScanManager] Subtitle counters reconciled: %s matched, %s unmatched.",
            matched,
            unmatched,
        )

    async def _stream_id_exists(self, channel: int, msg_id: int) -> bool:
        """Check normal IDs and members already stored in virtual split IDs."""
        try:
            stream_hash = await encode_string({"chat_id": channel, "msg_id": msg_id})
        except Exception:
            return False
        for index in range(1, self._db.current_db_index + 1):
            storage = self._db.dbs.get(f"storage_{index}")
            if storage is None:
                continue
            if await storage["movie"].find_one({"telegram.id": stream_hash}):
                return True
            if await storage["tv"].find_one({"seasons.episodes.telegram.id": stream_hash}):
                return True
            # Virtual split records keep part IDs inside `telegram.parts`.
            split_query = {"telegram.parts": {"$elemMatch": {"chat_id": channel, "msg_id": msg_id}}}
            if await storage["movie"].find_one(split_query):
                return True
            tv_split_query = {"seasons.episodes.telegram.parts": {"$elemMatch": {"chat_id": channel, "msg_id": msg_id}}}
            if await storage["tv"].find_one(tv_split_query):
                return True
        return False

    async def _quality_belongs_to_channel(self, quality: dict, channel_int: int) -> bool:
        """Return True when a normal or virtual split quality comes from channel."""
        try:
            decoded = await decode_string(quality.get("id") or "")
        except Exception:
            return False
        if not isinstance(decoded, dict):
            return False
        parts = decoded.get("parts") or []
        if parts:
            return any(int(str(part.get("chat_id", ""))) == channel_int for part in parts)
        try:
            return int(str(decoded.get("chat_id", ""))) == channel_int
        except (TypeError, ValueError):
            return False

    async def start(
        self,
        client,
        channels: List[str],
        mode: str = "scan",
        content_scope: str = "all",
        history_client=None,
    ) -> Dict[str, Any]:
        """Start or resume a media-only, subtitle-only, or combined scan.

        A subtitle rescan only clears subtitle index rows. A media rescan only
        clears movie/series entries. The all scope clears both.
        """
        async with self._lock:
            if self.state["status"] == "running":
                return {"ok": False, "message": "A channel scan is already running."}

            mode = str(mode or "scan").strip().lower()
            if mode not in {"scan", "rescan"}:
                return {"ok": False, "message": "Scan mode must be scan or rescan."}
            content_scope = self._normalise_scope(content_scope)
            channels = [str(channel).strip() for channel in (channels or []) if str(channel).strip()]

            can_resume = (
                mode == "scan"
                and self.state["status"] in ("paused", "cancelled")
                and bool(self.state["pending"])
                and self._normalise_scope(self.state.get("content_scope")) == content_scope
            )
            if mode == "scan" and not channels and can_resume:
                channels = list(self.state["pending"])
            if not channels:
                return {"ok": False, "message": "No channels selected."}

            cursor_map = self.state.setdefault("cursors", {}).setdefault(content_scope, {})
            if mode == "rescan":
                purged_media = purged_subtitles = 0
                for channel in channels:
                    try:
                        channel_int = int(str(channel).replace("-100", ""))
                    except ValueError:
                        LOGGER.warning(f"[ScanManager] Invalid channel id skipped: {channel}")
                        continue
                    # Keep media and subtitle cleanup independent. A failure in one
                    # must never leave stale rows from the other scope behind.
                    if content_scope in {"media", "all"}:
                        try:
                            purged_media += int(
                                await self._purge_media_channel_entries(channel_int) or 0
                            )
                        except Exception as exc:
                            LOGGER.error(
                                f"[ScanManager] media purge failed for {channel}: {exc}"
                            )
                    if content_scope in {"subtitles", "all"}:
                        try:
                            purged_subtitles += int(
                                await self._db.purge_subtitles_by_channel(channel_int) or 0
                            )
                        except Exception as exc:
                            LOGGER.error(
                                f"[ScanManager] subtitle purge failed for {channel}: {exc}"
                            )
                    cursor_map.pop(str(channel), None)

                self.state["selected_channels"] = list(channels)
                self.state["pending"] = list(channels)
                self.state["counters"] = self._blank_counters()
                self.state["subtitle_scanned_stream_ids"] = []
                LOGGER.info(
                    "[ScanManager] Rescan cleared %s media and %s subtitle records.",
                    purged_media,
                    purged_subtitles,
                )
            elif can_resume:
                pending = list(self.state["pending"])
                for channel in channels:
                    if channel not in pending:
                        pending.append(channel)
                self.state["pending"] = pending
                self.state["selected_channels"] = list(dict.fromkeys(self.state["selected_channels"] + channels))
            else:
                self.state["selected_channels"] = list(channels)
                self.state["pending"] = list(channels)
                self.state["counters"] = self._blank_counters()
                self.state["subtitle_scanned_stream_ids"] = []

            self.state["mode"] = mode
            self.state["content_scope"] = content_scope
            self.state["status"] = "running"
            self.state["phase"] = "scanning"
            self.state["error"] = None
            self.state["summary"] = ""
            self.state["current_channel"] = None
            self.state["current_channel_name"] = ""
            self.state["current_id"] = 0
            self.state["start_message_id"] = 0
            self.state["latest_message_id"] = 0
            self.state["tail_is_exact"] = False
            self.state["target_message_id"] = 0
            self.state["finished_at"] = 0.0
            self.state["started_at"] = _now()
            self._cancel = False
            await self._persist()
            self._task = asyncio.create_task(self._run(client, history_client=history_client))

            label = {"media": "Media", "subtitles": "Subtitle", "all": "Full"}[content_scope]
            prefix = "Rescan" if mode == "rescan" else "Scan"
            return {"ok": True, "message": f"{label} {prefix.lower()} started.", "status": self.get_status()}

    async def cancel(self) -> Dict[str, Any]:
        if self.state["status"] != "running":
            return {"ok": False, "message": "No channel scan is currently running."}
        self._cancel = True
        return {"ok": True, "message": "Stop requested — the scan will pause after the current batch."}

    async def _run(self, client, history_client=None) -> None:
        try:
            while self.state["pending"] and not self._cancel:
                channel = self.state["pending"][0]
                try:
                    channel_id = int(channel)
                except ValueError:
                    LOGGER.warning(f"[ScanManager] Invalid channel id skipped: {channel}")
                    self.state["pending"].pop(0)
                    await self._persist()
                    continue

                finished = await self._scan_channel(
                    client, channel_id, channel, history_client=history_client
                )
                if self._cancel:
                    break
                if finished and self.state["pending"] and self.state["pending"][0] == channel:
                    self.state["pending"].pop(0)
                    await self._persist()

            if self._cancel:
                self.state["status"] = "cancelled"
                self.state["phase"] = "idle"
                self.state["summary"] = "Scan stopped. Resume continues from the saved message cursor."
                LOGGER.info("[ScanManager] Scan cancelled by user (resumable).")
            else:
                # All channel messages are committed.  Keep the progress bar at
                # 99% while the final subtitle linking and counter reconciliation
                # complete, instead of showing a misleading 100% too early.
                self.state["phase"] = "finalizing"
                self.state["summary"] = "Finalizing subtitles and scan counters…"
                await self._persist()
                # Relink once at completion instead of after every media row.
                # This also links older subtitles when a media-only scan adds its
                # matching video later in the channel.
                result = await relink_unmatched_subtitles(self._db, limit=5000)
                self.state["counters"]["subtitles_relinked"] = int(result.get("linked") or 0)
                LOGGER.info(
                    "[ScanManager] Subtitle relink complete: %s linked from %s checked.",
                    result.get("linked", 0),
                    result.get("checked", 0),
                )
                await self._reconcile_subtitle_counters()
                self.state["status"] = "completed"
                self.state["phase"] = "idle"
                self.state["current_channel"] = None
                self.state["current_channel_name"] = ""
                processed = int(self.state["counters"].get("processed") or 0)
                if processed == 0:
                    self.state["summary"] = (
                        "No new messages found. Use Rescan to rebuild older channel posts."
                        if self.state.get("mode") == "scan"
                        else "No indexable messages were found in the selected channels."
                    )
                else:
                    self.state["summary"] = f"Scan complete — {processed} message(s) checked."
                LOGGER.info("[ScanManager] Scan completed. %s", self.state["summary"])
            self.state["finished_at"] = _now()
            await self._persist()

        except (ChannelPrivate, ChatAdminRequired) as exc:
            self.state["status"] = "error"
            self.state["phase"] = "idle"
            self.state["summary"] = "Scan could not access the selected channel."
            self.state["error"] = f"Access denied to channel — make sure the bot is an admin. ({exc})"
            self.state["finished_at"] = _now()
            LOGGER.error(f"[ScanManager] {self.state['error']}")
            await self._persist()
        except asyncio.CancelledError:
            await self._persist()
            raise
        except Exception as exc:
            self.state["status"] = "error"
            self.state["phase"] = "idle"
            self.state["summary"] = "Scan failed before it could finish."
            self.state["error"] = str(exc)
            self.state["finished_at"] = _now()
            LOGGER.error(f"[ScanManager] Unexpected error: {exc}")
            await self._persist()

    async def _latest_channel_message_id(self, client, chat_id: int) -> tuple[int, bool]:
        """Return ``(tail_id, is_exact)`` without advancing a scan cursor.

        A Telegram bot cannot call ``messages.GetHistory``. When that happens,
        return ``is_exact=False`` so callers can continue their safe explicit-ID
        scan, but the WebUI never mistakes the internal probe ceiling for the
        channel's final message ID.
        """
        try:
            history = client.get_chat_history(chat_id, limit=1)
            async for message in history:
                return int(getattr(message, "id", 0) or 0), True
            # The request itself worked and the channel is empty.
            return 0, True
        except (ChannelPrivate, ChatAdminRequired):
            raise
        except Exception as exc:
            LOGGER.warning(
                "[ScanManager] Could not read actual channel end ID for %s: %s",
                chat_id,
                exc,
            )
        return 0, False

    async def _scan_channel(
        self,
        client,
        chat_id: int,
        channel_key: str,
        history_client=None,
    ) -> bool:
        state = self.state
        cursor_map = self._cursor_map()
        try:
            chat = await client.get_chat(chat_id)
            state["current_channel_name"] = getattr(chat, "title", str(chat_id))
        except (ChannelPrivate, ChatAdminRequired):
            raise
        except Exception as exc:
            state["current_channel_name"] = str(chat_id)
            LOGGER.warning(f"[ScanManager] Could not resolve channel name for {chat_id}: {exc}")

        state["current_channel"] = channel_key
        scope = self._normalise_scope(state.get("content_scope"))

        # A real user session can read channel history and gives us an exact
        # tail. Bots cannot call messages.GetHistory, so the bot still fetches
        # explicit IDs while the user session is used only for the tail lookup.
        tail_client = history_client or client
        latest_id, tail_is_exact = await self._latest_channel_message_id(tail_client, chat_id)
        state["latest_message_id"] = latest_id
        state["tail_is_exact"] = tail_is_exact

        saved_cursor = int(cursor_map.get(str(channel_key), 1) or 1)
        current = max(1, saved_cursor)
        state["start_message_id"] = current

        # A stale cursor from the old empty-batch algorithm can be far beyond
        # the actual channel tail. Clamp it to the next real message position,
        # so the next upload is picked up by the normal Start Scan button.
        if tail_is_exact and current > latest_id + 1:
            LOGGER.info(
                "[ScanManager] Cursor for %s was ahead of channel tail (%s > %s); resetting to %s.",
                channel_key,
                current,
                latest_id,
                latest_id + 1,
            )
            current = latest_id + 1
            cursor_map[str(channel_key)] = current
            state["start_message_id"] = current

        # The scanner still needs a bounded explicit-ID range when running
        # bot-only. That range is intentionally internal: it is not the actual
        # channel end and must not be rendered as one in the WebUI.
        target_id = min(
            latest_id if tail_is_exact else current + (SCAN_BATCH_SIZE * SCAN_MAX_EMPTY_BATCHES),
            SCAN_MAX_ID_CAP,
        )
        state["target_message_id"] = target_id
        state["current_id"] = current

        LOGGER.info(
            "[ScanManager] Scanning %s (%s) from id %s to %s [%s]",
            state["current_channel_name"],
            chat_id,
            current,
            latest_id if tail_is_exact else "actual end unavailable (bot-only probe)",
            scope,
        )
        LOGGER.info(
            "[ScanManager] Fast metadata mode: %s parallel worker(s); ordered database commits.",
            SCAN_METADATA_CONCURRENCY,
        )

        # When the cursor is already at the exact channel tail, this is a valid
        # incremental scan with no new messages. Do not jump it forward again.
        if tail_is_exact and current > latest_id:
            state["current_id"] = latest_id
            cursor_map[str(channel_key)] = current
            await self._persist()
            LOGGER.info(
                "[ScanManager] No new messages in %s (cursor=%s, tail=%s).",
                state["current_channel_name"],
                current,
                latest_id,
            )
            return True

        # `upper_bound` is exclusive. This scans the exact tail when available,
        # otherwise a bounded bot-only probe window.
        upper_bound = min(target_id + 1, SCAN_MAX_ID_CAP + 1)
        empty_streak = 0
        batch_count = 0
        last_seen_message_id = current - 1

        while current < upper_bound:
            if self._cancel:
                return False

            batch_end = min(current + SCAN_BATCH_SIZE, upper_bound)
            batch_ids = list(range(current, batch_end))
            try:
                messages = await client.get_messages(chat_id, batch_ids)
            except FloodWait as exc:
                LOGGER.info(f"[ScanManager] FloodWait {exc.value}s — sleeping…")
                await asyncio.sleep(exc.value)
                continue
            except Exception as exc:
                LOGGER.error(f"[ScanManager] Batch fetch error at {current}: {exc}")
                state["counters"]["errors"] += 1
                current = batch_end
                empty_streak += 1
                # With no known tail, never advance the saved cursor over
                # unseen IDs after an error.  That would permanently skip a
                # future upload that uses one of those IDs.
                cursor_map[str(channel_key)] = (
                    current if tail_is_exact else max(saved_cursor, last_seen_message_id + 1)
                )
                state["current_id"] = min(batch_end - 1, target_id)
                await self._persist()
                if not tail_is_exact and empty_streak >= SCAN_MAX_EMPTY_BATCHES:
                    break
                continue

            if not isinstance(messages, list):
                messages = [messages]

            batch_had_content = False
            batch_messages: List[Any] = []
            for message in messages:
                if self._cancel:
                    cursor_map[str(channel_key)] = (
                        current if tail_is_exact else max(saved_cursor, last_seen_message_id + 1)
                    )
                    await self._persist()
                    return False
                if message is None or message.empty:
                    continue

                # Record the fetched message for cursor safety, but do not move
                # the visible progress position yet.  Fast workers may still be
                # resolving metadata, so the UI advances only after their ordered
                # database commit has completed.
                message_id = int(getattr(message, "id", 0) or current)
                last_seen_message_id = max(last_seen_message_id, message_id)
                batch_had_content = True
                state["counters"]["total_found"] += 1
                batch_messages.append(message)

            # Metadata lookup is the slow path. Resolve a few files in parallel,
            # then commit their database updates in their original Telegram order.
            if batch_messages:
                # The ordered commit gate advances Processed/current message only
                # after each message has really finished indexing.
                await self._process_messages_fast(batch_messages, chat_id)

            empty_streak = 0 if batch_had_content else empty_streak + 1
            current = batch_end
            cursor_map[str(channel_key)] = (
                current if tail_is_exact else max(saved_cursor, last_seen_message_id + 1)
            )
            # Empty batches also advance the visible live position, but only
            # the saved cursor uses the safe last-seen rule above.
            state["current_id"] = min(batch_end - 1, target_id)
            batch_count += 1
            if batch_count % SCAN_PERSIST_EVERY == 0:
                await self._persist()
            if not tail_is_exact and empty_streak >= SCAN_MAX_EMPTY_BATCHES:
                break
            if current < upper_bound:
                await asyncio.sleep(SCAN_BATCH_DELAY)

        await self._persist()
        LOGGER.info(f"[ScanManager] Finished {state['current_channel_name']} at id {min(current - 1, target_id)}")
        return True

    async def _process_messages_fast(self, messages: List[Any], chat_id: int) -> None:
        """Resolve a Telegram batch concurrently while preserving commit order."""
        if not messages:
            return

        gate = _OrderedBatchCommit()
        limiter = asyncio.Semaphore(SCAN_METADATA_CONCURRENCY)

        async def worker(slot: int, message: Any) -> None:
            async with limiter:
                await self._process_message(
                    message,
                    chat_id,
                    commit_gate=gate,
                    commit_slot=slot,
                )

        results = await asyncio.gather(
            *(worker(slot, message) for slot, message in enumerate(messages)),
            return_exceptions=True,
        )
        for result in results:
            if isinstance(result, BaseException):
                LOGGER.error("[ScanManager] Fast worker failed: %s", result)
                self.state["counters"]["errors"] += 1

    async def _process_message(
        self,
        message,
        chat_id: int,
        *,
        commit_gate: _OrderedBatchCommit | None = None,
        commit_slot: int | None = None,
    ) -> None:
        entered_commit = False

        async def _enter_commit() -> None:
            nonlocal entered_commit
            if commit_gate is not None and not entered_commit:
                await commit_gate.wait_turn(int(commit_slot or 0))
                entered_commit = True

        try:
            state = self.state
            scope = self._normalise_scope(state.get("content_scope"))

            if message.document and is_subtitle_file(
                message.document.file_name or message.caption or "",
                message.document.mime_type or "",
            ):
                if scope == "media":
                    return
                state["counters"]["subtitles_found"] += 1
                try:
                    channel_int = int(str(chat_id).replace("-100", ""))
                    await _enter_commit()
                    record = await index_subtitle(
                        self._db,
                        channel=channel_int,
                        msg_id=message.id,
                        filename=message.document.file_name or message.caption or "subtitle.srt",
                        caption=message.caption or "",
                        raw_size=message.document.file_size or 0,
                        size=get_readable_file_size(message.document.file_size or 0),
                        mime_type=message.document.mime_type or "",
                    )
                    self._track_scanned_subtitle(record)
                    state["counters"]["subtitles_indexed"] += 1
                    state["counters"]["subtitles_replaced"] += int(record.get("replaced_count") or 0)
                    if record.get("status") == "matched":
                        state["counters"]["subtitles_matched"] += 1
                        media = record.get("media") or {}
                        LOGGER.info(
                            "[ScanManager] Subtitle indexed: %s [%s] → %s [%s]",
                            record.get("filename") or "subtitle",
                            record.get("language_code") or "und",
                            media.get("title") or "media",
                            media.get("imdb_id") or "no-imdb",
                        )
                    else:
                        state["counters"]["subtitles_unmatched"] += 1
                        detected = record.get("detected") or {}
                        LOGGER.info(
                            "[ScanManager] Subtitle indexed: %s [%s] → unmatched (title: %s)",
                            record.get("filename") or "subtitle",
                            record.get("language_code") or "und",
                            detected.get("title") or "unknown",
                        )
                except Exception as exc:
                    LOGGER.error(f"[ScanManager] Subtitle index error msg {message.id}: {exc}")
                    state["counters"]["errors"] += 1
                return

            is_video = bool(message.video)
            file = message.video or message.document
            raw_file_name = getattr(file, "file_name", "") or ""
            caption = message.caption or ""
            title = caption or raw_file_name or "video.mkv"
            file_name = raw_file_name or title
            split_source, split_info = find_split_source(
                raw_file_name,
                caption,
                file_name,
                title,
                clean_filename(raw_file_name),
                clean_filename(caption),
            )

            # Full rescans used to rely only on filename matching.  Reuse the
            # live-upload MIME-aware fallback so generic `.zip.001` files remain
            # supported after restarting the bot or pressing Scan All.
            document_mime = getattr(message.document, "mime_type", "") or ""
            if not split_info:
                mime_split = detect_split_upload(raw_file_name, document_mime)
                if mime_split:
                    split_source, split_info = raw_file_name, mime_split

            is_video_document = False
            if message.document and not is_video:
                mime_type = document_mime
                # Split ZIP chunks are usually application/zip or octet-stream,
                # not video/*, so the filename detector is equally authoritative.
                is_video_document = mime_type.startswith("video/") or bool(split_info)

            if not (is_video or is_video_document):
                if scope != "subtitles":
                    state["counters"]["skipped_nonvid"] += 1
                return
            if scope == "subtitles":
                return

            metadata_source = split_source or (file_name if split_info else title)
            msg_id = message.id
            raw_size = getattr(file, "file_size", 0) or 0
            size = get_readable_file_size(raw_size)
            channel_int = int(str(chat_id).replace("-100", ""))

            try:
                if await self._stream_id_exists(channel_int, msg_id):
                    state["counters"]["skipped_dup"] += 1
                    return
            except Exception as exc:
                LOGGER.warning(f"[ScanManager] Duplicate check error msg {msg_id}: {exc}")

            try:
                # Keep the original split volume name for metadata parsing. Besides
                # preserving the part suffix, this keeps the live-upload and rescan
                # group keys identical when filename cleanup removes codec tags.
                metadata_input = metadata_source if split_info else clean_filename(metadata_source)
                metadata_info = await metadata(metadata_input, channel_int, msg_id)
            except Exception as exc:
                LOGGER.warning(f"[ScanManager] Metadata exception for msg {msg_id}: {exc}")
                metadata_info = None
            if metadata_info is None:
                state["counters"]["skipped_meta"] += 1
                return

            title_clean = remove_urls(metadata_source if metadata_info.get("group_key") else title)

            # Historical scans can see the part suffix only after rebuilding the
            # display filename. Recover it here, before a 937 MB final part gets
            # written as an ordinary single-file stream.
            if not metadata_info.get("group_key"):
                extension_suffix = "" if title_clean.lower().endswith((".mkv", ".mp4", ".avi", ".ts", ".m4v", ".mov", ".wmv", ".webm", ".flv", ".mpeg", ".mpg")) else ".mkv"
                _, recovered_split = find_split_source(
                    title_clean,
                    f"{title_clean}{extension_suffix}",
                    file_name,
                    raw_file_name,
                    caption,
                )
                if recovered_split:
                    metadata_info.update(split_metadata_fields(
                        channel_int,
                        metadata_info.get("quality"),
                        recovered_split,
                    ))
                    LOGGER.info(
                        "[SplitRecovery] msg %s: %s → part %s (media: %s)",
                        msg_id,
                        title_clean,
                        recovered_split.part_number,
                        recovered_split.media_filename,
                    )

            if metadata_info.get("group_key"):
                title_clean = metadata_info.get("media_filename") or strip_part_suffix(title_clean)
            if not title_clean.lower().endswith((".mkv", ".mp4", ".avi", ".ts", ".m4v", ".mov", ".wmv", ".webm", ".flv", ".mpeg", ".mpg")):
                title_clean += ".mkv"
            try:
                await _enter_commit()
                updated_id = await self._db.insert_media(
                    metadata_info,
                    channel=channel_int,
                    msg_id=msg_id,
                    size=size,
                    raw_size=raw_size,
                    name=title_clean,
                )
                if updated_id:
                    state["counters"]["indexed"] += 1
                    if metadata_info.get("group_key"):
                        LOGGER.info(
                            "[ScanManager] Split part indexed: %s (part %s)",
                            title_clean,
                            metadata_info.get("part_number") or 1,
                        )
                    elif metadata_info.get("media_type") == "tv":
                        LOGGER.info(
                            "[ScanManager] TV episode indexed: %s S%02dE%02d (msg %s)",
                            metadata_info.get("title") or "TV",
                            int(metadata_info.get("season_number") or 0),
                            int(metadata_info.get("episode_number") or 0),
                            msg_id,
                        )
                    else:
                        LOGGER.info(
                            "[ScanManager] Movie indexed: %s (msg %s)",
                            metadata_info.get("title") or "Movie",
                            msg_id,
                        )
                else:
                    state["counters"]["skipped_meta"] += 1
            except Exception as exc:
                LOGGER.error(f"[ScanManager] Database insert error msg {msg_id}: {exc}")
                state["counters"]["errors"] += 1

        finally:
            # Invalid files and metadata failures still advance the ordered gate;
            # otherwise later workers would wait forever behind an early return.
            if commit_gate is not None:
                if not entered_commit:
                    await _enter_commit()
                # Commit slots are ordered, so this is the exact point at which
                # the visible progress position can safely advance.  Do not let
                # the bar reach the batch tail merely because metadata work was
                # queued ahead of these completed commits.
                message_id = int(getattr(message, "id", 0) or 0)
                if message_id:
                    self.state["current_id"] = message_id
                counters = self.state.setdefault("counters", {})
                counters["processed"] = int(counters.get("processed") or 0) + 1
                self.state["updated_at"] = _now()
                await commit_gate.finish(int(commit_slot or 0))

    async def _purge_media_channel_entries(self, channel_int: int) -> int:
        """Remove only media rows for one channel; subtitles are handled separately."""
        purged = 0
        for index in range(1, self._db.current_db_index + 1):
            storage = self._db.dbs.get(f"storage_{index}")
            if storage is None:
                continue

            async for movie in storage["movie"].find({}):
                remaining = []
                changed = False
                for quality in movie.get("telegram", []):
                    if await self._quality_belongs_to_channel(quality, channel_int):
                        purged += 1
                        changed = True
                        continue
                    remaining.append(quality)
                if changed:
                    if remaining:
                        movie["telegram"] = remaining
                        await storage["movie"].replace_one({"_id": movie["_id"]}, movie)
                    else:
                        await storage["movie"].delete_one({"_id": movie["_id"]})

            async for tv in storage["tv"].find({}):
                changed = False
                for season in tv.get("seasons", []):
                    for episode in season.get("episodes", []):
                        remaining = []
                        for quality in episode.get("telegram", []):
                            if await self._quality_belongs_to_channel(quality, channel_int):
                                purged += 1
                                changed = True
                                continue
                            remaining.append(quality)
                        episode["telegram"] = remaining
                    season["episodes"] = [episode for episode in season["episodes"] if episode.get("telegram")]
                tv["seasons"] = [season for season in tv["seasons"] if season.get("episodes")]
                if changed:
                    if tv["seasons"]:
                        await storage["tv"].replace_one({"_id": tv["_id"]}, tv)
                    else:
                        await storage["tv"].delete_one({"_id": tv["_id"]})
        return purged

# ═════════════════════════════════════════════════════════════════════════════
#  DbCheckManager — integrity checker + dead-link purge
# ═════════════════════════════════════════════════════════════════════════════
class DbCheckManager:
    def __init__(self) -> None:
        self._db = None
        self._task: Optional[asyncio.Task] = None
        self._cancel = False
        self._lock = asyncio.Lock()
        self.state: Dict[str, Any] = self._blank_state()

    @staticmethod
    def _blank_state() -> Dict[str, Any]:
        return {
            "status": "idle",   # idle|running|completed|cancelled|error
            "checked": 0,
            "alive": 0,
            "dead": 0,
            "errors": 0,
            "purged": 0,
            "speed": 0,
            "dead_entries": [],   # [{"id": hash, "title": str}]
            "started_at": 0.0,
            "finished_at": 0.0,
            "error": None,
        }

    def bind_db(self, db) -> None:
        self._db = db

    def get_status(self) -> Dict[str, Any]:
        s = self.state
        elapsed = 0.0
        if s["started_at"]:
            end = s["finished_at"] or _now()
            elapsed = max(0.0, end - s["started_at"])
        return {
            "status": s["status"],
            "is_running": s["status"] == "running",
            "checked": s["checked"],
            "alive": s["alive"],
            "dead": s["dead"],
            "errors": s["errors"],
            "purged": s["purged"],
            "speed": s["speed"],
            "dead_count": len(s["dead_entries"]),
            "dead_entries": list(s["dead_entries"]),
            "elapsed": _fmt_elapsed(elapsed),
            "elapsed_seconds": int(elapsed),
            "error": s["error"],
        }

    # ── Control ───────────────────────────────────────────────────────────────
    async def start(self, client) -> Dict[str, Any]:
        async with self._lock:
            if self.state["status"] == "running":
                return {"ok": False, "message": "A DB check is already running."}
            self.state = self._blank_state()
            self.state["status"] = "running"
            self.state["started_at"] = _now()
            self._cancel = False
            # DbCheckManager only verifies explicit stored message IDs.
            # It does not use GetHistory, so there is no history_client here.
            self._task = asyncio.create_task(self._run(client))
            return {"ok": True, "message": "DB check started.", "status": self.get_status()}

    async def cancel(self) -> Dict[str, Any]:
        if self.state["status"] != "running":
            return {"ok": False, "message": "No DB check is currently running."}
        self._cancel = True
        return {"ok": True, "message": "Stop requested — finishing the current batch."}

    # ── Single-message check ───────────────────────────────────────────────────
    async def _check_message(self, client, stream_hash: str):
        try:
            decoded = await decode_string(stream_hash)
            # split files store a parts list — every part must be alive
            if isinstance(decoded, dict) and "parts" in decoded:
                parts = decoded.get("parts") or []
                if not parts:
                    return False
                for part in parts:
                    alive = await self._check_one(client, part.get("chat_id"), part.get("msg_id"))
                    if alive is None:
                        return None
                    if not alive:
                        return False
                return True
            return await self._check_one(client, decoded.get("chat_id"), decoded.get("msg_id"))
        except FloodWait as e:
            await asyncio.sleep(e.value)
            return await self._check_message(client, stream_hash)
        except Exception:
            return None

    async def _check_one(self, client, chat_id, msg_id):
        if chat_id is None or msg_id is None:
            return False
        try:
            raw_chat_id = str(chat_id)
            normalized_chat_id = int(raw_chat_id) if raw_chat_id.startswith("-100") else int(f"-100{raw_chat_id}")
            message_id = int(msg_id)
            result = await client.get_messages(normalized_chat_id, message_ids=[message_id])
            msg = result[0] if isinstance(result, (list, tuple)) and result else result
            if msg is None or getattr(msg, "empty", False):
                return False
            return bool(getattr(msg, "video", None) or getattr(msg, "document", None) or getattr(msg, "audio", None))
        except FloodWait as e:
            await asyncio.sleep(e.value)
            return await self._check_one(client, chat_id, msg_id)
        except Exception:
            return None

    async def _process_batch(self, client, batch: List[str]):
        tasks = [self._check_message(client, h) for h in batch]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def _record_results(self, batch: List[str], results) -> None:
        s = self.state
        for stream_hash, result in zip(batch, results):
            s["checked"] += 1
            if result is True:
                s["alive"] += 1
            elif result is False:
                s["dead"] += 1
                title = None
                try:
                    title = await self._db.get_title_by_stream_id(stream_hash)
                except Exception:
                    pass
                s["dead_entries"].append({"id": stream_hash, "title": title or "Unknown"})
            else:
                s["errors"] += 1
        elapsed = max(1, int(_now() - s["started_at"]))
        s["speed"] = s["checked"] // elapsed

    # ── Worker ──────────────────────────────────────────────────────────────────
    async def _run(self, client, history_client=None) -> None:
        db = self._db
        s = self.state
        try:
            for i in range(1, db.current_db_index + 1):
                storage = db.dbs.get(f"storage_{i}")
                if storage is None:
                    continue

                # Movies
                last_id = None
                while not self._cancel:
                    query = {"_id": {"$gt": last_id}} if last_id else {}
                    docs = await storage["movie"].find(query).sort("_id", 1) \
                        .limit(DBCHECK_PAGE_SIZE).to_list(length=DBCHECK_PAGE_SIZE)
                    if not docs:
                        break
                    for movie in docs:
                        last_id = movie["_id"]
                        stream_ids = [q.get("id") for q in movie.get("telegram", []) if q.get("id")]
                        for x in range(0, len(stream_ids), DBCHECK_CONCURRENCY):
                            if self._cancel:
                                break
                            batch = stream_ids[x:x + DBCHECK_CONCURRENCY]
                            results = await self._process_batch(client, batch)
                            await self._record_results(batch, results)
                            await asyncio.sleep(DBCHECK_BATCH_DELAY)

                # TV
                last_id = None
                while not self._cancel:
                    query = {"_id": {"$gt": last_id}} if last_id else {}
                    docs = await storage["tv"].find(query).sort("_id", 1) \
                        .limit(DBCHECK_PAGE_SIZE).to_list(length=DBCHECK_PAGE_SIZE)
                    if not docs:
                        break
                    for show in docs:
                        last_id = show["_id"]
                        stream_ids = []
                        for season in show.get("seasons", []):
                            for episode in season.get("episodes", []):
                                for q in episode.get("telegram", []):
                                    if q.get("id"):
                                        stream_ids.append(q["id"])
                        for x in range(0, len(stream_ids), DBCHECK_CONCURRENCY):
                            if self._cancel:
                                break
                            batch = stream_ids[x:x + DBCHECK_CONCURRENCY]
                            results = await self._process_batch(client, batch)
                            await self._record_results(batch, results)
                            await asyncio.sleep(DBCHECK_BATCH_DELAY)

            s["status"] = "cancelled" if self._cancel else "completed"
            s["finished_at"] = _now()
            LOGGER.info(f"[DbCheck] {s['status']} — checked {s['checked']}, dead {s['dead']}")
        except asyncio.CancelledError:
            s["status"] = "cancelled"
            s["finished_at"] = _now()
            raise
        except Exception as e:
            s["status"] = "error"
            s["error"] = str(e)
            s["finished_at"] = _now()
            LOGGER.error(f"[DbCheck] Error: {e}")

    # ── Purge ────────────────────────────────────────────────────────────────────
    async def purge(self, stream_ids: Optional[List[str]] = None) -> Dict[str, Any]:
        """Delete the given dead stream entries (defaults to the ones found in the
        last check). Returns how many were purged."""
        db = self._db
        if stream_ids is None:
            stream_ids = [d["id"] for d in self.state.get("dead_entries", [])]
        stream_ids = [h for h in stream_ids if h]
        if not stream_ids:
            return {"ok": False, "message": "No dead links to purge.", "purged": 0}

        purged = 0
        for x in range(0, len(stream_ids), DBCHECK_CONCURRENCY):
            batch = stream_ids[x:x + DBCHECK_CONCURRENCY]
            results = await asyncio.gather(
                *[db.delete_media_by_stream_id(h) for h in batch],
                return_exceptions=True,
            )
            purged += sum(1 for r in results if r is True)

        # Drop purged ids from the in-memory dead list
        purged_set = set(stream_ids)
        self.state["dead_entries"] = [
            d for d in self.state.get("dead_entries", []) if d["id"] not in purged_set
        ]
        self.state["purged"] = self.state.get("purged", 0) + purged
        return {"ok": True, "message": f"Purged {purged} dead entr{'y' if purged == 1 else 'ies'}.",
                "purged": purged}


# ── Singletons ──────────────────────────────────────────────────────────────
scan_manager = ScanManager()
dbcheck_manager = DbCheckManager()
