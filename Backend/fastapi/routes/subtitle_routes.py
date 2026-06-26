"""Stremio subtitle resource endpoints kept separate from stream/catalog code."""
from __future__ import annotations

from pathlib import PurePath
from urllib.parse import unquote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from Backend import db
from Backend.fastapi.security.tokens import verify_token
from Backend.helper.subtitle_constants import language_name
from Backend.helper.public_url import delivery_url
from Backend.logger import LOGGER

router = APIRouter(prefix="/stremio", tags=["Stremio Subtitles"])


def _safe_delivery_name(subtitle: dict) -> str:
    filename = PurePath(subtitle.get("filename") or "subtitle.srt").name
    extension = subtitle.get("extension") or PurePath(filename).suffix or ".srt"
    if not filename.lower().endswith(extension.lower()):
        filename = f"{filename}{extension}"
    return filename.replace("/", "_").replace("\\", "_")


def _subtitle_target_id(raw_id: str) -> tuple[str, int | None, int | None]:
    """Parse a Stremio movie/episode ID without depending on request extras."""
    parts = unquote(raw_id or "").split(":")
    imdb_id = (parts[0] if parts else "").strip().lower()
    if not imdb_id:
        raise HTTPException(status_code=400, detail="Missing Stremio subtitle ID.")
    try:
        season = int(parts[1]) if len(parts) > 1 and parts[1] else None
        episode = int(parts[2]) if len(parts) > 2 and parts[2] else None
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid Stremio subtitle ID.") from exc
    return imdb_id, season, episode


# Stremio normally appends stream identification context after the title ID:
# /subtitles/movie/tt123/filename=video.mkv&videoSize=...&videoHash=....json
# The context is useful to remote subtitle providers but this library maps
# subtitles by title/episode, so it is accepted and intentionally ignored.
@router.get("/{token}/subtitles/{media_type}/{id}/{extra:path}.json")
@router.get("/{token}/subtitle/{media_type}/{id}/{extra:path}.json", include_in_schema=False)
@router.get("/{token}/subtitles/{media_type}/{id}.json")
@router.get("/{token}/subtitle/{media_type}/{id}.json", include_in_schema=False)
async def get_subtitles(
    token: str,
    media_type: str,
    id: str,
    request: Request,
    extra: str = "",
    _: dict = Depends(verify_token),
):
    """Return title/episode subtitles in Stremio format.

    Linked subtitles are returned for every video quality of the same movie or
    episode. ``extra`` is accepted for Stremio's filename/videoSize/videoHash
    context and is not used as a quality filter.
    """
    if media_type not in {"movie", "series"}:
        raise HTTPException(status_code=404, detail="Invalid Stremio media type.")

    imdb_id, season, episode = _subtitle_target_id(id)

    if media_type == "series" and (season is None or episode is None):
        LOGGER.info(
            "[Stremio] subtitles response: imdb=%s type=%s matched=0 context=%s missing_episode=true",
            imdb_id,
            media_type,
            "yes" if extra else "no",
        )
        return JSONResponse(
            content={"subtitles": []},
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    subtitles = await db.get_subtitles_for_stremio(
        imdb_id=imdb_id,
        media_type=media_type,
        season=season,
        episode=episode,
    )

    result = []
    for subtitle in subtitles:
        filename = _safe_delivery_name(subtitle)
        code = subtitle.get("language_code") or "und"
        display_name = subtitle.get("language_name") or language_name(code)
        result.append({
            "id": f"telegram-subtitle-{subtitle.get('db_index')}-{subtitle.get('_id')}",
            "url": delivery_url(request, token, subtitle["stream_id"], filename),
            "lang": code,
            "label": f"{display_name} · {filename}",
        })

    LOGGER.info(
        "[Stremio] subtitles response: imdb=%s type=%s matched=%s context=%s",
        imdb_id,
        media_type,
        len(result),
        "yes" if extra else "no",
    )
    return JSONResponse(
        content={"subtitles": result},
        headers={"Cache-Control": "no-store, max-age=0"},
    )
