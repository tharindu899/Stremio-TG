"""Business logic that indexes, matches, and re-links subtitle records."""
from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from Backend.helper.encrypt import encode_string
from Backend.helper.subtitle_models import SubtitleIdentity
from Backend.helper.subtitle_parser import parse_subtitle_identity
from Backend.logger import LOGGER

# Provider resolution is only a fallback after the indexed-media lookup fails.
# It bridges title aliases (for example a romanized Japanese filename to an
# English metadata title) without creating media rows or trusting a remote
# result unless that exact IMDb/TMDb record already exists in the local library.
_SUBTITLE_PROVIDER_CACHE: dict[tuple[str, int | None, int | None, int | None], dict[str, Any]] = {}
_SUBTITLE_PROVIDER_CACHE_LIMIT = 1024
_SUBTITLE_PROVIDER_SEMAPHORE = asyncio.Semaphore(3)


def _provider_cache_key(reference: dict[str, Any]) -> tuple[str, int | None, int | None, int | None]:
    title = str(reference.get("normalized_title") or reference.get("title") or "").casefold().strip()

    def as_int(value: Any) -> int | None:
        try:
            return int(value) if value not in (None, "") else None
        except (TypeError, ValueError):
            return None

    return (
        title,
        as_int(reference.get("release_year") or reference.get("year")),
        as_int(reference.get("season")),
        as_int(reference.get("episode")),
    )


def _provider_reference(metadata: dict[str, Any], original: dict[str, Any]) -> dict[str, Any]:
    return {
        "imdb_id": metadata.get("imdb_id") or None,
        "tmdb_id": metadata.get("tmdb_id"),
        "title": metadata.get("title") or original.get("title") or "",
        "normalized_title": metadata.get("title") or original.get("normalized_title") or "",
        "release_year": metadata.get("year") or original.get("release_year"),
        "season": original.get("season"),
        "episode": original.get("episode"),
    }


async def _resolve_alias_target(db, reference: dict[str, Any]) -> dict[str, Any] | None:
    """Resolve a subtitle's title through providers, then require a local ID hit."""
    if reference.get("imdb_id") or reference.get("tmdb_id") not in (None, ""):
        return None

    title = str(reference.get("title") or "").strip()
    normalized = str(reference.get("normalized_title") or "").strip()
    if len(normalized.replace(" ", "")) < 3:
        return None

    cache_key = _provider_cache_key(reference)
    provider_hit = _SUBTITLE_PROVIDER_CACHE.get(cache_key)
    if provider_hit:
        return await db.resolve_subtitle_target(provider_hit)

    try:
        year = cache_key[1]
        season = cache_key[2]
        episode = cache_key[3]
        async with _SUBTITLE_PROVIDER_SEMAPHORE:
            # Import lazily: subtitle parsing stays lightweight and avoids a
            # module cycle during application startup.
            from Backend.helper.metadata import fetch_movie_metadata, fetch_tv_metadata

            if season is not None and episode is not None:
                metadata = await fetch_tv_metadata(
                    title,
                    season,
                    episode,
                    encoded_string="",
                    year=year,
                )
            else:
                metadata = await fetch_movie_metadata(
                    title,
                    encoded_string="",
                    year=year,
                )
                # A subtitle without S/E can still belong to a series-level
                # record.  Keep this fallback after movie matching so normal
                # movie names never become a TV false positive.
                if metadata is None:
                    metadata = await fetch_tv_metadata(
                        title,
                        1,
                        1,
                        encoded_string="",
                        year=year,
                    )
    except Exception as exc:
        LOGGER.debug("[SubtitleMatch] Provider alias lookup failed for %r: %s", title, exc)
        return None

    if not metadata:
        return None

    provider_hit = _provider_reference(metadata, reference)
    if not provider_hit.get("imdb_id") and provider_hit.get("tmdb_id") in (None, ""):
        return None

    # Cache successful provider identity only.  Local media may be indexed a
    # few seconds later, so caching a miss would make the later relink fail.
    if len(_SUBTITLE_PROVIDER_CACHE) >= _SUBTITLE_PROVIDER_CACHE_LIMIT:
        _SUBTITLE_PROVIDER_CACHE.pop(next(iter(_SUBTITLE_PROVIDER_CACHE)))
    _SUBTITLE_PROVIDER_CACHE[cache_key] = provider_hit

    target = await db.resolve_subtitle_target(provider_hit)
    if target:
        LOGGER.info(
            "[SubtitleMatch] Alias resolved: %r → %r [%s]",
            title,
            target.get("title") or "media",
            target.get("imdb_id") or target.get("tmdb_id") or "no-id",
        )
    return target


async def resolve_subtitle_target(db, reference: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    """Resolve locally first, then bridge registered metadata aliases safely."""
    target = await db.resolve_subtitle_target(reference)
    if target:
        return target, str(reference.get("match_hint") or "filename")

    target = await _resolve_alias_target(db, reference)
    if target:
        return target, "metadata_alias"
    return None, "unmatched"


async def index_subtitle(
    db,
    *,
    channel: int,
    msg_id: int,
    filename: str,
    caption: str,
    raw_size: int,
    size: str,
    mime_type: str = "",
) -> dict[str, Any]:
    """Create or refresh one subtitle index record from a Telegram document."""
    identity = parse_subtitle_identity(filename, caption)
    stream_id = await encode_string({"chat_id": int(channel), "msg_id": int(msg_id)})
    target, match_method = await resolve_subtitle_target(db, identity.to_dict())
    now = datetime.utcnow()

    document = {
        "stream_id": stream_id,
        "chat_id": int(channel),
        "msg_id": int(msg_id),
        "filename": identity.source_filename,
        "caption": identity.source_caption,
        "extension": identity.extension,
        "mime_type": mime_type or "",
        "raw_size": int(raw_size or 0),
        "size": size or "0B",
        "language_code": identity.language_code,
        "language_name": identity.language_name,
        "detected": identity.to_dict(),
        "media": target or {},
        "status": "matched" if target else "unmatched",
        "match_method": match_method,
        "updated_at": now,
    }
    return await db.upsert_subtitle(document)


async def relink_unmatched_subtitles(db, limit: int = 500) -> dict[str, int]:
    """Try to attach pending subtitle records after new videos are indexed."""
    documents = await db.get_unmatched_subtitles(limit=max(1, min(int(limit), 5000)))
    linked = 0
    for subtitle in documents:
        # Reparse every unmatched row.  Matching rules improve over time and
        # keeping stale parsed release tags (for example "DUAL AUDIO 10bit")
        # would otherwise prevent a later Start Scan from repairing an older
        # subtitle without an expensive full subtitle rescan.
        identity = parse_subtitle_identity(
            subtitle.get("filename") or "",
            subtitle.get("caption") or "",
        )
        detected = identity.to_dict()
        subtitle["detected"] = detected

        target, match_method = await resolve_subtitle_target(db, detected)
        if not target:
            # Refresh legacy rows too, so older `und` records receive the
            # Sinhala fallback without changing their unmatched status.
            await db.refresh_subtitle_detection(
                db_index=int(subtitle["db_index"]),
                subtitle_id=str(subtitle["_id"]),
                detected=detected,
            )
            continue
        changed = await db.set_subtitle_match(
            db_index=int(subtitle["db_index"]),
            subtitle_id=str(subtitle["_id"]),
            media=target,
            match_method="relinked_alias" if match_method == "metadata_alias" else "relinked",
            language_code=identity.language_code,
            detected=detected,
        )
        linked += int(bool(changed))
    return {"checked": len(documents), "linked": linked}


async def apply_manual_match(db, *, db_index: int, subtitle_id: str, payload: dict) -> dict[str, Any] | None:
    """Validate a WebUI manual mapping against already indexed media."""
    if payload.get("unlink"):
        return await db.clear_subtitle_match(db_index=db_index, subtitle_id=subtitle_id)

    reference = {
        "imdb_id": (payload.get("imdb_id") or "").strip().lower() or None,
        "tmdb_id": payload.get("tmdb_id"),
        "title": (payload.get("title") or "").strip(),
        "normalized_title": (payload.get("title") or "").strip(),
        "season": payload.get("season"),
        "episode": payload.get("episode"),
    }
    target = await db.resolve_subtitle_target(reference)
    if not target:
        return None

    return await db.set_subtitle_match(
        db_index=db_index,
        subtitle_id=subtitle_id,
        media=target,
        match_method="manual",
        language_code=payload.get("language_code"),
    )
