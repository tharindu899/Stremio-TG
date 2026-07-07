"""Caption / filename tag rules for custom Stremio catalogs.

A rule belongs to one normal custom catalog.  Rules never share the catalog's
manual ``items`` array: matching results are written to ``rule_items`` instead.
That separation makes rule changes reversible and keeps owner-curated titles
safe.
"""
from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any, Iterable

from bson import ObjectId

from Backend.logger import LOGGER


_TAG_SYNC_STATE_ID = "tag_catalog_sync"
_tag_sync_lock = asyncio.Lock()


def _now() -> datetime:
    return datetime.utcnow()


def _media_type(doc: dict) -> str:
    return "tv" if doc.get("media_type") in {"tv", "series"} else "movie"


def _item_key(item: dict) -> tuple[str, int, int]:
    return (
        "tv" if item.get("media_type") in {"tv", "series"} else "movie",
        int(item.get("tmdb_id") or 0),
        int(item.get("db_index") or 1),
    )


def _doc_item(doc: dict) -> dict:
    return {
        "tmdb_id": int(doc.get("tmdb_id") or 0),
        "db_index": int(doc.get("db_index") or 1),
        "media_type": _media_type(doc),
        "added_at": _now(),
    }


def _unique_items(items: Iterable[dict]) -> list[dict]:
    result: list[dict] = []
    seen: set[tuple[str, int, int]] = set()
    for item in items or []:
        try:
            key = _item_key(item)
        except (TypeError, ValueError):
            continue
        if not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(dict(item))
    return result


def _normalise_text(value: object) -> str:
    """Make punctuation, dots and line breaks behave like word separators."""
    text = str(value or "").casefold()
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def clean_rule_tags(value: object) -> list[str]:
    """Accept comma/newline-separated phrases, preserving readable labels."""
    if isinstance(value, str):
        candidates = re.split(r"[,\n\r]+", value)
    elif isinstance(value, list):
        candidates = value
    else:
        candidates = []

    cleaned: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        label = re.sub(r"\s+", " ", str(candidate or "")).strip()
        normalized = _normalise_text(label)
        if not normalized or len(normalized) > 100 or normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(label[:100])
        if len(cleaned) >= 30:
            break
    return cleaned


def _iter_quality_rows(doc: dict):
    if _media_type(doc) == "movie":
        yield from (doc.get("telegram") or [])
        return
    for season in doc.get("seasons") or []:
        for episode in season.get("episodes") or []:
            yield from (episode.get("telegram") or [])


def build_rule_source(doc: dict) -> str:
    """Text indexed for tag matching.

    New uploads keep their Telegram caption and filename on the quality row.
    Older rows still work through title/genres/the saved stream filename.
    """
    pieces: list[object] = [
        doc.get("title"),
        doc.get("original_title"),
        doc.get("original_name"),
        doc.get("genres"),
        doc.get("manual_tags"),
        doc.get("tags"),
    ]
    for quality in _iter_quality_rows(doc):
        if not isinstance(quality, dict):
            continue
        pieces.extend([
            quality.get("source_caption"),
            quality.get("source_filename"),
            quality.get("name"),
            quality.get("media_filename"),
            quality.get("legacy_source_filename"),
        ])

    flattened: list[str] = []
    for piece in pieces:
        if isinstance(piece, (list, tuple, set)):
            flattened.extend(str(value or "") for value in piece)
        else:
            flattened.append(str(piece or ""))
    return _normalise_text(" \n ".join(flattened))


def document_matches_tags(doc: dict, tags: Iterable[str]) -> bool:
    source = f" {build_rule_source(doc)} "
    for tag in clean_rule_tags(list(tags)):
        phrase = _normalise_text(tag)
        if phrase and f" {phrase} " in source:
            return True
    return False


def _catalog_rule(catalog: dict) -> dict:
    rule = catalog.get("tag_rule") or {}
    return {
        "enabled": bool(rule.get("enabled")),
        "tags": clean_rule_tags(rule.get("tags") or []),
        "updated_at": rule.get("updated_at"),
    }


async def _write_status(db, payload: dict) -> None:
    await db.dbs["tracking"]["state"].update_one(
        {"_id": _TAG_SYNC_STATE_ID}, {"$set": payload}, upsert=True
    )


async def get_tag_catalog_sync_status(db) -> dict:
    doc = await db.dbs["tracking"]["state"].find_one({"_id": _TAG_SYNC_STATE_ID}) or {}
    doc.pop("_id", None)
    return {
        "running": bool(doc.get("running")),
        "scanned": int(doc.get("scanned") or 0),
        "matched": int(doc.get("matched") or 0),
        "catalogs": int(doc.get("catalogs") or 0),
        "message": doc.get("message") or "Ready",
        "started_at": doc.get("started_at"),
        "finished_at": doc.get("finished_at"),
        "error": doc.get("error"),
    }


async def get_catalog_tag_rule(db, catalog_id: str) -> dict | None:
    try:
        catalog = await db.dbs["tracking"]["custom_catalogs"].find_one({"_id": ObjectId(catalog_id)})
    except Exception:
        return None
    if not catalog:
        return None
    return {
        "catalog_id": str(catalog["_id"]),
        "catalog_name": catalog.get("name") or "Catalog",
        "available": not bool(catalog.get("auto")),
        "rule": _catalog_rule(catalog),
    }


async def update_catalog_tag_rule(
    db,
    catalog_id: str,
    tags: object,
    enabled: object = True,
) -> dict | None:
    """Save the matching phrases for one manual catalog.

    Automatic TMDb shelves deliberately reject tag rules because their contents
    are owned by the TMDb sync process.
    """
    try:
        object_id = ObjectId(catalog_id)
    except Exception:
        return None

    catalog = await db.dbs["tracking"]["custom_catalogs"].find_one({"_id": object_id})
    if not catalog or catalog.get("auto"):
        return None

    cleaned = clean_rule_tags(tags)
    active = bool(enabled) and bool(cleaned)
    now = _now()
    await db.dbs["tracking"]["custom_catalogs"].update_one(
        {"_id": object_id},
        {
            "$set": {
                "tag_rule": {"enabled": active, "tags": cleaned, "updated_at": now},
                "updated_at": now,
            }
        },
    )
    return await get_catalog_tag_rule(db, catalog_id)


async def _all_rule_catalogs(db) -> list[dict]:
    cursor = db.dbs["tracking"]["custom_catalogs"].find({"auto": {"$ne": True}})
    catalogs = await cursor.to_list(None)
    return [catalog for catalog in catalogs if _catalog_rule(catalog)["enabled"]]


async def _iter_media(db):
    for db_index in range(1, int(db.current_db_index) + 1):
        storage = db.dbs.get(f"storage_{db_index}")
        if storage is None:
            continue
        for collection_name in ("movie", "tv"):
            cursor = storage[collection_name].find({"tmdb_id": {"$exists": True, "$ne": None}})
            async for doc in cursor:
                doc["db_index"] = int(doc.get("db_index") or db_index)
                doc["media_type"] = "tv" if collection_name == "tv" else "movie"
                yield doc


def _merged_count(catalog: dict, rule_items: list[dict]) -> int:
    manual_items = catalog.get("manual_items") if "manual_items" in catalog else catalog.get("items")
    return len(_unique_items([*(manual_items or []), *rule_items]))


async def run_tag_catalog_sync(db, *, force: bool = False) -> dict:
    # Never queue a second full database walk. A completed/current run already
    # reads the latest rule records before it writes its result.
    if _tag_sync_lock.locked():
        return {"running": True, "message": "Caption tag sync is already running."}

    async with _tag_sync_lock:
        started_at = _now()
        await _write_status(db, {
            "running": True,
            "scanned": 0,
            "matched": 0,
            "catalogs": 0,
            "message": "Reading media captions and filenames…",
            "started_at": started_at,
            "finished_at": None,
            "error": None,
        })
        scanned = 0
        matched = 0
        try:
            active_catalogs = await _all_rule_catalogs(db)
            all_manual_catalogs = await db.dbs["tracking"]["custom_catalogs"].find({"auto": {"$ne": True}}).to_list(None)
            buckets: dict[ObjectId, list[dict]] = {catalog["_id"]: [] for catalog in active_catalogs}

            async for document in _iter_media(db):
                scanned += 1
                item = _doc_item(document)
                for catalog in active_catalogs:
                    rule = _catalog_rule(catalog)
                    if document_matches_tags(document, rule["tags"]):
                        buckets[catalog["_id"]].append(item)
                        matched += 1
                if scanned % 100 == 0:
                    await _write_status(db, {
                        "running": True,
                        "scanned": scanned,
                        "matched": matched,
                        "catalogs": len(active_catalogs),
                        "message": "Reading media captions and filenames…",
                        "started_at": started_at,
                        "finished_at": None,
                        "error": None,
                    })

            collection = db.dbs["tracking"]["custom_catalogs"]
            now = _now()
            for catalog in all_manual_catalogs:
                items = _unique_items(buckets.get(catalog["_id"], []))
                await collection.update_one(
                    {"_id": catalog["_id"]},
                    {"$set": {
                        "rule_items": items,
                        "rule_item_count": len(items),
                        "item_count": _merged_count(catalog, items),
                        "updated_at": now,
                    }},
                )

            summary = {
                "running": False,
                "scanned": scanned,
                "matched": matched,
                "catalogs": len(active_catalogs),
                "message": (
                    f"Caption tag sync complete · {matched} match"
                    f"{'es' if matched != 1 else ''} across {len(active_catalogs)} rule"
                    f"{'s' if len(active_catalogs) != 1 else ''}."
                ),
                "started_at": started_at,
                "finished_at": _now(),
                "error": None,
            }
            await _write_status(db, summary)
            LOGGER.info("Caption tag catalog sync complete: %s", summary)
            return summary
        except Exception as exc:
            summary = {
                "running": False,
                "scanned": scanned,
                "matched": matched,
                "catalogs": 0,
                "message": "Caption tag sync failed.",
                "started_at": started_at,
                "finished_at": _now(),
                "error": str(exc),
            }
            await _write_status(db, summary)
            LOGGER.exception("Caption tag catalog sync failed")
            return summary


async def start_tag_catalog_sync_background(db, *, force: bool = False) -> dict:
    # The in-process lock is authoritative. Persisted `running` status can be
    # stale after a Space/container restart, so it must not block a recovery sync.
    if _tag_sync_lock.locked():
        return {"started": False, "message": "Caption tag sync is already running."}
    asyncio.create_task(run_tag_catalog_sync(db))
    return {"started": True, "message": "Caption tag sync started."}


async def sync_tag_catalog_for_identity(db, media_type: str, tmdb_id: int) -> None:
    """Refresh one title's automatic rule membership after a live upload.

    This is intentionally best-effort; indexing a Telegram media item must never
    fail merely because a catalog rule update is unavailable.
    """
    try:
        normalized_type = "tv" if str(media_type).lower() in {"tv", "series"} else "movie"
        document = None
        for db_index in range(1, int(db.current_db_index) + 1):
            storage = db.dbs.get(f"storage_{db_index}")
            if storage is None:
                continue
            document = await storage[normalized_type].find_one({"tmdb_id": int(tmdb_id)})
            if document:
                document["db_index"] = int(document.get("db_index") or db_index)
                document["media_type"] = normalized_type
                break
        if not document:
            return

        catalogs = await _all_rule_catalogs(db)
        if not catalogs:
            return
        item = _doc_item(document)
        collection = db.dbs["tracking"]["custom_catalogs"]
        now = _now()

        for catalog in catalogs:
            rule = _catalog_rule(catalog)
            item_match = document_matches_tags(document, rule["tags"])
            identity = {
                "tmdb_id": item["tmdb_id"],
                "db_index": item["db_index"],
                "media_type": item["media_type"],
            }
            if item_match:
                await collection.update_one(
                    {
                        "_id": catalog["_id"],
                        "rule_items": {"$not": {"$elemMatch": identity}},
                    },
                    {"$push": {"rule_items": {"$each": [item], "$position": 0}}, "$set": {"updated_at": now}},
                )
            else:
                await collection.update_one(
                    {"_id": catalog["_id"]},
                    {"$pull": {"rule_items": identity}, "$set": {"updated_at": now}},
                )
    except Exception as exc:
        LOGGER.debug("Tag catalog refresh skipped for %s %s: %s", media_type, tmdb_id, exc)
