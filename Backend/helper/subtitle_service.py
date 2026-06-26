"""Business logic that indexes, matches, and re-links subtitle records."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from Backend.helper.encrypt import encode_string
from Backend.helper.subtitle_models import SubtitleIdentity
from Backend.helper.subtitle_parser import parse_subtitle_identity


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
    target = await db.resolve_subtitle_target(identity.to_dict())
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
        "match_method": identity.match_hint if target else "unmatched",
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

        target = await db.resolve_subtitle_target(detected)
        if not target:
            continue
        changed = await db.set_subtitle_match(
            db_index=int(subtitle["db_index"]),
            subtitle_id=str(subtitle["_id"]),
            media=target,
            match_method="relinked",
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
