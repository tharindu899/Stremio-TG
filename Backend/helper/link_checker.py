import asyncio
from typing import AsyncIterator, Optional

from Backend.logger import LOGGER
from Backend.helper.encrypt import decode_string


class DeadLinkChecker:
    """Periodically validate Telegram media references without holding Mongo cursors open.

    A health pass can take several minutes because each Telegram message is checked
    separately. Keyset pagination keeps Mongo cursors short-lived, so Atlas cannot
    invalidate the scan halfway through with ``CursorNotFound``.
    """

    PAGE_SIZE = 50
    CHECK_DELAY_SECONDS = 0.5

    def __init__(self, db, app, check_interval_hours: int = 24):
        self.db = db
        self.app = app
        self.check_interval_seconds = check_interval_hours * 3600
        self.is_running = False

    async def start(self):
        if self.is_running:
            return
        self.is_running = True
        LOGGER.info(
            "Started Dead Link Checker background task (Interval: %ss)",
            self.check_interval_seconds,
        )
        asyncio.create_task(self._run_loop())

    async def _run_loop(self):
        # Wait a minute before starting the first scan so the bots can boot up.
        await asyncio.sleep(60)

        while self.is_running:
            # Replace mode can intentionally delete the previous Telegram source
            # while a rescan is rebuilding its replacement stream. Running a
            # health check in that window would create false dead links.
            try:
                from Backend.helper.scan_manager import scan_manager
                if scan_manager.get_status().get("is_running"):
                    LOGGER.info("Dead Link Checker postponed: media scan is running.")
                    await asyncio.sleep(30)
                    continue
            except Exception:
                # Health checks should still work if the optional scanner is
                # unavailable during early application startup.
                pass

            try:
                LOGGER.info("Starting Dead Link Checker scan...")
                await self._scan_all_media()
                LOGGER.info("Dead Link Checker scan complete.")
            except Exception as exc:
                LOGGER.error("Error in Dead Link Checker loop: %s", exc)

            await asyncio.sleep(self.check_interval_seconds)

    async def _iter_documents(self, collection, query: dict) -> AsyncIterator[dict]:
        """Yield matching documents using small keyset-paginated Mongo pages.

        The prior implementation kept one cursor open while sleeping after every
        Telegram request. Atlas may close such a cursor before the scan reaches
        its tail, which produced recurring ``CursorNotFound`` errors.
        """
        last_id = None
        while True:
            page_query = dict(query)
            if last_id is not None:
                page_query["_id"] = {"$gt": last_id}

            cursor = (
                collection.find(page_query)
                .sort("_id", 1)
                .limit(self.PAGE_SIZE)
            )
            page = await cursor.to_list(length=self.PAGE_SIZE)
            if not page:
                return

            last_id = page[-1].get("_id")
            for document in page:
                yield document

            if len(page) < self.PAGE_SIZE:
                return

    async def _scan_all_media(self):
        from Backend.pyrofork.bot import multi_clients

        if not multi_clients:
            LOGGER.warning("No bot clients available for Dead Link Checker.")
            return

        client = multi_clients.get(0) or next(iter(multi_clients.values()))

        for db_index in range(1, self.db.current_db_index + 1):
            db_key = f"storage_{db_index}"
            active_db = self.db.dbs[db_key]
            await self._scan_movies(active_db, client, db_index)
            await self._scan_tv(active_db, client, db_index)

    async def _scan_movies(self, active_db, client, db_index: int) -> None:
        query = {
            "telegram": {"$exists": True, "$not": {"$size": 0}},
            "telegram.is_dead": {"$ne": True},
        }
        try:
            async for movie in self._iter_documents(active_db["movie"], query):
                tmdb_id = movie.get("tmdb_id")
                for quality in movie.get("telegram", []):
                    if quality.get("is_dead"):
                        continue
                    alive = await self._check_file_alive(client, quality.get("id"))
                    if alive is False:
                        LOGGER.warning(
                            "Found dead link for Movie %s (Quality: %s)",
                            tmdb_id,
                            quality.get("quality"),
                        )
                        await self.db.flag_dead_link(
                            "movie", tmdb_id, db_index, quality.get("id")
                        )
                    await asyncio.sleep(self.CHECK_DELAY_SECONDS)
        except Exception as exc:
            LOGGER.error("Error scanning movies in DB %s: %s", db_index, exc)

    async def _scan_tv(self, active_db, client, db_index: int) -> None:
        query = {
            "seasons.episodes.telegram": {"$exists": True, "$not": {"$size": 0}},
            "seasons.episodes.telegram.is_dead": {"$ne": True},
        }
        try:
            async for tv in self._iter_documents(active_db["tv"], query):
                tmdb_id = tv.get("tmdb_id")
                for season in tv.get("seasons", []):
                    for episode in season.get("episodes", []):
                        for quality in episode.get("telegram", []):
                            if quality.get("is_dead"):
                                continue
                            alive = await self._check_file_alive(client, quality.get("id"))
                            if alive is False:
                                LOGGER.warning(
                                    "Found dead link for TV %s S%sE%s (Quality: %s)",
                                    tmdb_id,
                                    season.get("season_number"),
                                    episode.get("episode_number"),
                                    quality.get("quality"),
                                )
                                await self.db.flag_dead_link(
                                    "tv", tmdb_id, db_index, quality.get("id")
                                )
                            await asyncio.sleep(self.CHECK_DELAY_SECONDS)
        except Exception as exc:
            LOGGER.error("Error scanning TV shows in DB %s: %s", db_index, exc)

    async def _check_file_alive(self, client, quality_id: str) -> Optional[bool]:
        """Return True, False for a confirmed missing message, or None to retry later.

        Transient Telegram or network failures must not be converted into a
        permanent dead-link flag.
        """
        try:
            decoded = await decode_string(quality_id)
            if not decoded:
                return False

            if "parts" in decoded:
                parts = decoded.get("parts") or []
                if not parts:
                    return False
                for part in parts:
                    status = await self._check_single_message(
                        client, part.get("chat_id"), part.get("msg_id")
                    )
                    if status is not True:
                        return status
                return True

            if "chat_id" not in decoded or "msg_id" not in decoded:
                return False
            return await self._check_single_message(
                client, decoded["chat_id"], decoded["msg_id"]
            )
        except Exception as exc:
            LOGGER.warning(
                "Link checker postponed one record after a temporary resolution error: %s",
                exc,
            )
            return None

    async def _check_single_message(self, client, chat_id, msg_id) -> Optional[bool]:
        if chat_id is None or msg_id is None:
            return False

        try:
            raw_chat_id = str(chat_id)
            normalized_chat_id = (
                int(raw_chat_id)
                if raw_chat_id.startswith("-100")
                else int(f"-100{raw_chat_id}")
            )
            message_id = int(msg_id)
            result = await client.get_messages(
                normalized_chat_id, message_ids=[message_id]
            )
        except Exception as exc:
            LOGGER.warning(
                "Link checker postponed Telegram message %s/%s: %s",
                chat_id,
                msg_id,
                exc,
            )
            return None

        message = result[0] if isinstance(result, (list, tuple)) and result else result
        if message is None or getattr(message, "empty", False):
            return False
        return bool(
            getattr(message, "document", None)
            or getattr(message, "video", None)
            or getattr(message, "audio", None)
        )
