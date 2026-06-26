"""Authenticated WebUI APIs for the local Telegram subtitle library."""
from __future__ import annotations

from fastapi import HTTPException

from Backend import db
from Backend.helper.subtitle_constants import language_name
from Backend.helper.subtitle_parser import normalize_language
from Backend.helper.subtitle_service import apply_manual_match, relink_unmatched_subtitles


async def list_subtitles_api(
    page: int = 1,
    page_size: int = 50,
    search: str = "",
    status: str = "all",
    language: str = "",
) -> dict:
    return await db.list_subtitles(
        page=page,
        page_size=page_size,
        search=search,
        status=status,
        language=language,
    )


async def subtitle_stats_api() -> dict:
    stats = await db.get_subtitle_stats()
    stats["language_labels"] = {
        code: language_name(code) for code in stats.get("languages", {})
    }
    return stats


async def update_subtitle_api(db_index: int, subtitle_id: str, payload: dict) -> dict:
    has_target_reference = bool(
        payload.get("unlink")
        or payload.get("imdb_id")
        or payload.get("tmdb_id")
        or payload.get("title")
    )

    if has_target_reference:
        result = await apply_manual_match(
            db,
            db_index=int(db_index),
            subtitle_id=subtitle_id,
            payload=payload,
        )
        if not result:
            raise HTTPException(
                status_code=404,
                detail="No indexed movie or episode matched that link. Index the video first, then try again.",
            )
        return {"message": "Subtitle updated.", "subtitle": result}

    if "language_code" in payload:
        code = normalize_language(payload.get("language_code"))
        result = await db.update_subtitle_language(
            db_index=int(db_index), subtitle_id=subtitle_id, language_code=code
        )
        if not result:
            raise HTTPException(status_code=404, detail="Subtitle not found.")
        return {"message": "Subtitle language updated.", "subtitle": result}

    raise HTTPException(status_code=400, detail="Choose a language or provide a media link.")


async def relink_subtitles_api(payload: dict | None = None) -> dict:
    payload = payload or {}
    try:
        limit = int(payload.get("limit", 500))
    except (TypeError, ValueError):
        limit = 500
    result = await relink_unmatched_subtitles(db, limit=limit)
    return {"message": f"Checked {result['checked']} unmatched subtitles; linked {result['linked']}.", **result}


async def delete_subtitle_api(db_index: int, subtitle_id: str) -> dict:
    deleted = await db.delete_subtitle(db_index=int(db_index), subtitle_id=subtitle_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subtitle not found.")
    return {"message": "Subtitle removed from the index. The Telegram file was not deleted."}
