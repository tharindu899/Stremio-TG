import re
import time
from datetime import date, datetime, timedelta, timezone
from typing import Optional
from urllib.parse import quote, unquote

import PTN
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
from pyrogram.enums import ChatMemberStatus
from pyrogram.errors import UserNotParticipant

from Backend import __version__, db
from Backend.config import Telegram
from Backend.fastapi.security.tokens import verify_token
from Backend.fastapi.themes import DEFAULT_THEME, get_theme
from Backend.helper.global_search import global_search, is_global_search_enabled
from Backend.helper.imdb import get_detail, get_season
from Backend.helper.metadata import format_imdb_images, resolve_cover_url
from Backend.helper.settings_manager import SettingsManager
from Backend.helper.subtitles import get_subtitles_for, stremio_subtitle_entries
from Backend.logger import LOGGER
from Backend.pyrofork.bot import StreamBot, get_streambot_url

router = APIRouter(prefix="/stremio", tags=["Stremio Addon"])
templates = Jinja2Templates(directory="Backend/fastapi/templates")

#----- Addon configuration
ADDON_NAME = "Telegram"
ADDON_VERSION = __version__
PAGE_SIZE = 15

_membership_cache: dict = {}
_MEMBERSHIP_TTL = 60
_MEMBERSHIP_CACHE_MAX = 5000

# Cinemeta metadata is only used as an artwork/episode fallback here.  Keep a
# modest in-process cache so opening a long-running anime series does not fetch
# the same 100s of episode records on every Stremio request.
_provider_series_cache: dict[str, tuple[float, dict]] = {}
_PROVIDER_SERIES_TTL = 6 * 60 * 60
_PROVIDER_SERIES_CACHE_MAX = 250


#----- Drop cached membership results for one user or all users
def invalidate_membership_cache(user_id: int | None = None) -> None:
    if user_id is None:
        _membership_cache.clear()
        return
    for key in [k for k in _membership_cache if k[1] == user_id]:
        _membership_cache.pop(key, None)


#----- Effective (mode, allowed_tokens) for a title, honouring per-item overrides
def _effective_visibility(catalog: dict, item: dict) -> tuple:
    if item.get("visibility") in ("public", "tokens", "owner"):
        return item["visibility"], (item.get("allowed_tokens") or [])
    return (catalog.get("visibility") or "public"), (catalog.get("allowed_tokens") or [])


#----- Whether a token may see content with the given visibility
def _token_can_view(mode: str, allowed_tokens: list, token_data: dict) -> bool:
    user_id = token_data.get("user_id")
    try:
        if user_id is not None and int(user_id) == int(Telegram.OWNER_ID):
            return True
    except (TypeError, ValueError):
        pass
    if mode == "owner":
        return False
    if mode == "tokens":
        return token_data.get("token") in (allowed_tokens or [])
    if SettingsManager.current().subscription:
        return not token_data.get("subscription_expired")
    return True


#----- Mongo filter that hides owner-only / restricted titles from a token
def _visibility_query(token_data: dict) -> dict:
    user_id = token_data.get("user_id")
    try:
        if user_id is not None and int(user_id) == int(Telegram.OWNER_ID):
            return {}
    except (TypeError, ValueError):
        pass
    return {"$or": [
        {"visibility": {"$exists": False}},
        {"visibility": "public"},
        {"visibility": "tokens", "allowed_tokens": token_data.get("token")},
    ]}


#----- Hide titles locked to a single catalog from default listings / search
def _not_exclusive_clause(allow_searchable: bool = False) -> dict:
    ors = [{"exclusive_catalog_id": {"$exists": False}}, {"exclusive_catalog_id": None}]
    if allow_searchable:
        ors.append({"exclusive_searchable": True})
    return {"$or": ors}


#----- Combine non-empty Mongo filters under a single $and
def _merge_filters(*filters) -> dict:
    parts = [f for f in filters if f]
    if not parts:
        return {}
    return parts[0] if len(parts) == 1 else {"$and": parts}


#----- Whether a title (by imdb id) may be seen by this token, honouring its own visibility
async def _title_allowed(imdb_id: str, token_data: dict) -> bool:
    doc = await db.get_media_details(imdb_id=imdb_id)
    if not doc:
        return True
    return _token_can_view(doc.get("visibility") or "public", doc.get("allowed_tokens") or [], token_data)


#----- Available catalog genres
GENRES = [
    "Action", "Adventure", "Animation", "Biography", "Comedy",
    "Crime", "Documentary", "Drama", "Family", "Fantasy",
    "History", "Horror", "Music", "Mystery", "Romance",
    "Sci-Fi", "Sport", "Thriller", "War", "Western"
]


#----- Turn a stored image reference into an absolute URL for Stremio clients.
#----- Rebinds gradient covers and app-served /thumb paths to the current hosts.
def _abs_media_url(value: str) -> str:
    value = resolve_cover_url(value)
    idx = value.find("/thumb/")
    return f"{SettingsManager.current().base_url}{value[idx:]}" if idx != -1 else value


def _is_nonempty_url(value) -> bool:
    return bool(str(value or "").strip())


def _provider_video_map(provider_meta: dict | None) -> dict[tuple[int, int], dict]:
    mapped: dict[tuple[int, int], dict] = {}
    for video in (provider_meta or {}).get("videos") or []:
        if not isinstance(video, dict):
            continue
        try:
            key = (int(video.get("season")), int(video.get("episode")))
        except (TypeError, ValueError):
            continue
        mapped[key] = video
    return mapped


async def _get_provider_series_meta(imdb_id: str) -> dict:
    """Fetch/cached Cinemeta series metadata for missing artwork fallbacks.

    The local database remains the source of truth.  This helper only fills
    absent poster/backdrop/episode thumbnail values, including absolute anime
    episodes such as Naruto episode 500 and season-zero specials.
    """
    imdb_id = str(imdb_id or "").strip()
    if not imdb_id:
        return {}

    now = time.time()
    cached = _provider_series_cache.get(imdb_id)
    if cached and now - cached[0] < _PROVIDER_SERIES_TTL:
        return cached[1]

    try:
        provider = await get_detail(imdb_id=imdb_id, media_type="tvSeries") or {}
    except Exception as exc:
        LOGGER.debug("[Stremio] artwork provider lookup failed for %s: %s", imdb_id, exc)
        provider = {}

    if len(_provider_series_cache) >= _PROVIDER_SERIES_CACHE_MAX:
        oldest = min(_provider_series_cache, key=lambda key: _provider_series_cache[key][0])
        _provider_series_cache.pop(oldest, None)
    _provider_series_cache[imdb_id] = (now, provider)
    return provider


#----- Map an internal media item into a Stremio meta object
def convert_to_stremio_meta(item: dict) -> dict:
    media_type = "series" if item.get("media_type") == "tv" else "movie"

    meta = {
        "id": item.get('imdb_id'),
        "type": media_type,
        "name": item.get("title"),
        "poster": _abs_media_url(item.get("poster")),
        "logo": item.get("logo") or "",
        "year": item.get("release_year"),
        "releaseInfo": str(item.get("release_year", "")),
        "imdb_id": item.get("imdb_id", ""),
        "moviedb_id": item.get("tmdb_id", ""),
        "background": _abs_media_url(item.get("backdrop")),
        "genres": item.get("genres") or [],
        "imdbRating": str(item.get("rating") or ""),
        "description": item.get("description") or "",
        "cast": item.get("cast") or [],
        "runtime": item.get("runtime") or "",
    }
    return meta


#----- Format a movie release date as an ISO string, or None
def format_released_date(media):
    year = media.get("release_year")
    if year:
        try:
            return datetime(int(year), 1, 1, tzinfo=timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        except Exception:
            return None
    return None


def _stremio_iso_date(value, fallback: datetime | None = None) -> str:
    """Return a strict ISO-8601 UTC timestamp accepted by Stremio video metadata."""
    fallback = fallback or (datetime.now(timezone.utc) - timedelta(days=1))

    parsed: datetime | None = None
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime(value.year, value.month, value.day, 5, 0, tzinfo=timezone.utc)
    elif isinstance(value, (int, float)):
        try:
            stamp = float(value)
            if stamp > 10_000_000_000:
                stamp /= 1000.0
            parsed = datetime.fromtimestamp(stamp, tz=timezone.utc)
        except (OverflowError, OSError, TypeError, ValueError):
            parsed = None
    elif value not in (None, ""):
        raw = str(value).strip()
        try:
            if re.fullmatch(r"\d{10,13}", raw):
                stamp = float(raw)
                if len(raw) >= 13:
                    stamp /= 1000.0
                parsed = datetime.fromtimestamp(stamp, tz=timezone.utc)
            else:
                normalized = raw.replace("/", "-")
                if normalized.endswith("Z"):
                    normalized = normalized[:-1] + "+00:00"
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", normalized):
                    parsed = datetime.strptime(normalized, "%Y-%m-%d").replace(
                        hour=5, tzinfo=timezone.utc
                    )
                else:
                    parsed = datetime.fromisoformat(normalized)
        except (OverflowError, OSError, TypeError, ValueError):
            parsed = None

    if parsed is None:
        parsed = fallback
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _clean_meta_text(value, default: str = "") -> str:
    if value is None:
        return default
    text = str(value).strip()
    return text or default


#----- Build a Stremio stream display name/title from a filename
def format_stream_details(filename: str, quality: str, size: str, is_split: bool = False) -> tuple[str, str]:
    size_emoji = "📦" if is_split else "💾"
    try:
        parsed = PTN.parse(filename)
    except Exception:
        return (f"Telegram {quality}", f"📁 {filename}\n{size_emoji} {size}")

    codec_parts = []
    if parsed.get("codec"):
        codec_parts.append(f"🎥 {parsed.get('codec')}")
    if parsed.get("bitDepth"):
        codec_parts.append(f"🌈 {parsed.get('bitDepth')}bit")
    if parsed.get("audio"):
        codec_parts.append(f"🔊 {parsed.get('audio')}")
    if parsed.get("encoder"):
        codec_parts.append(f"👤 {parsed.get('encoder')}")

    codec_info = " ".join(codec_parts) if codec_parts else ""

    resolution = parsed.get("resolution", quality)
    quality_type = parsed.get("quality", "")
    stream_name = f"Telegram {resolution} {quality_type}".strip()

    stream_title_parts = [
        f"📁 {filename}",
        f"{size_emoji} {size}",
    ]
    if codec_info:
        stream_title_parts.append(codec_info)

    stream_title = "\n".join(stream_title_parts)
    return (stream_name, stream_title)


def parse_size_to_bytes(size_str: str) -> int:
    if not size_str:
        return 0
    match = re.match(r"([\d.]+)\s*([A-Za-z]+)", size_str.strip())
    if not match:
        return 0
    value, unit = float(match.group(1)), match.group(2).upper()
    multipliers = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    return int(value * multipliers.get(unit, 1))


def get_resolution_priority(stream_name: str) -> int:
    resolution_map = {
        "2160p": 2160, "4k": 2160, "uhd": 2160,
        "1080p": 1080, "fhd": 1080,
        "720p": 720, "hd": 720,
        "480p": 480, "sd": 480,
        "360p": 360,
    }
    for res_key, res_value in resolution_map.items():
        if res_key in stream_name.lower():
            return res_value
    return 1


#----- Manifest describing the addon's catalogs/resources for this token
@router.get("/{token}/manifest.json")
async def get_manifest(token: str, token_data: dict = Depends(verify_token)):
    if SettingsManager.current().hide_catalog:
        resources = ["stream", "subtitles"]
        catalogs = []
    else:
        resources = ["catalog", "meta", "stream", "subtitles"]
        catalogs = [
            {
                "type": "movie",
                "id": "latest_movies",
                "name": "Latest",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": GENRES},
                    {"name": "skip"}
                ],
                "extraSupported": ["genre", "skip"]
            },
            {
                "type": "movie",
                "id": "top_movies",
                "name": "Popular",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": GENRES},
                    {"name": "skip"},
                    {"name": "search", "isRequired": False}
                ],
                "extraSupported": ["genre", "skip", "search"]
            },
            {
                "type": "series",
                "id": "latest_series",
                "name": "Latest",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": GENRES},
                    {"name": "skip"}
                ],
                "extraSupported": ["genre", "skip"]
            },
            {
                "type": "series",
                "id": "top_series",
                "name": "Popular",
                "extra": [
                    {"name": "genre", "isRequired": False, "options": GENRES},
                    {"name": "skip"},
                    {"name": "search", "isRequired": False}
                ],
                "extraSupported": ["genre", "skip", "search"]
            }
        ]

        try:
            custom_catalogs = await db.get_custom_catalogs()
            for catalog in custom_catalogs:
                visible_items = [
                    i for i in (catalog.get("items") or [])
                    if _token_can_view(*_effective_visibility(catalog, i), token_data)
                ]
                has_movie = any(i.get("media_type") == "movie" for i in visible_items)
                has_series = any(i.get("media_type") == "tv" for i in visible_items)
                if not has_movie and not has_series:
                    continue
                catalog_id = str(catalog.get("_id"))
                catalog_name = catalog.get("name") or "Custom Catalog"
                if has_movie:
                    catalogs.append({
                        "type": "movie",
                        "id": f"custom_{catalog_id}",
                        "name": catalog_name,
                        "extra": [{"name": "skip"}],
                        "extraSupported": ["skip"],
                    })
                if has_series:
                    catalogs.append({
                        "type": "series",
                        "id": f"custom_{catalog_id}",
                        "name": catalog_name,
                        "extra": [{"name": "skip"}],
                        "extraSupported": ["skip"],
                    })
        except Exception:
            pass


    addon_name = ADDON_NAME
    addon_desc = "Streams movies and series from your Telegram."
    addon_version = ADDON_VERSION

    #----- Show expiry info in the addon: token's own expiry first, else the subscription
    try:
        expiry_obj = token_data.get("expires_at")
        if expiry_obj is None and SettingsManager.current().subscription:
            user_id = token_data.get("user_id")
            if user_id:
                user = await db.get_user(int(user_id))
                if user and user.get("subscription_status") == "active":
                    expiry_obj = user.get("subscription_expiry")

        if expiry_obj:
            expiry_str = expiry_obj.strftime("%d %b %Y").lstrip("0")
            addon_desc = (
                f"📅 Access active until {expiry_str}.\n"
                f"Streams movies and series from your Telegram."
            )
            epoch_tag = format(int(expiry_obj.timestamp()) & 0xFFFF, "x")
            addon_version = f"{ADDON_VERSION}-{epoch_tag}"
    except Exception:
        pass

    return {
        "id": f"telegram.media.{token[:8]}",
        "version": addon_version,
        "name": addon_name,
        "logo": "https://i.postimg.cc/XqWnmDXr/Picsart-25-10-09-08-09-45-867.png",
        "description": addon_desc,
        "types": ["movie", "series"],
        "resources": resources,
        "catalogs": catalogs,
        "idPrefixes": ["tt", "tg"],
        "behaviorHints": {
            "configurable": True,
            "configurationRequired": False
        },
        "config": [
            {
                "key": "manifest_url",
                "title": "Your Addon URL (copy to reinstall)",
                "type": "text",
                "default": f"{SettingsManager.current().base_url}/stremio/{token}/manifest.json"
            }
        ]
    }


#----- Catalog listing (latest/popular/custom, with genre/search/skip)
@router.get("/{token}/catalog/{media_type}/{id}/{extra:path}.json")
@router.get("/{token}/catalog/{media_type}/{id}.json")
async def get_catalog(token: str, media_type: str, id: str, extra: Optional[str] = None, token_data: dict = Depends(verify_token)):
    if SettingsManager.current().hide_catalog:
        raise HTTPException(status_code=404, detail="Catalog disabled")

    if media_type not in ["movie", "series"]:
        raise HTTPException(status_code=404, detail="Invalid catalog type")

    genre_filter = None
    search_query = None
    stremio_skip = 0

    if extra:
        params = extra.replace("&", "/").split("/")
        for param in params:
            if param.startswith("genre="):
                genre_filter = unquote(param.removeprefix("genre="))
            elif param.startswith("search="):
                search_query = unquote(param.removeprefix("search="))
            elif param.startswith("skip="):
                try:
                    stremio_skip = int(param.removeprefix("skip="))
                except ValueError:
                    stremio_skip = 0

    page = (stremio_skip // PAGE_SIZE) + 1

    try:
        if id.startswith("custom_"):
            catalog_id = id.removeprefix("custom_")
            catalog = await db.get_custom_catalog(catalog_id)
            if not catalog:
                return {"metas": []}

            db_media_type = "tv" if media_type == "series" else "movie"
            visible_items = [
                it for it in (catalog.get("items") or [])
                if it.get("media_type") == db_media_type
                and _token_can_view(*_effective_visibility(catalog, it), token_data)
            ]
            visible_items.sort(key=lambda it: it.get("updated_on") or it.get("added_at") or datetime.min, reverse=True)
            start = (page - 1) * PAGE_SIZE
            items = await db.get_documents(visible_items[start:start + PAGE_SIZE])
            items = [it for it in items if _token_can_view(it.get("visibility") or "public", it.get("allowed_tokens") or [], token_data)]
        elif search_query:
            search_results = await db.search_documents(
                query=search_query, page=page, page_size=PAGE_SIZE,
                extra_filter=_merge_filters(_visibility_query(token_data), _not_exclusive_clause(allow_searchable=True)),
            )
            all_items = search_results.get("results", [])
            db_media_type = "tv" if media_type == "series" else "movie"
            items = [item for item in all_items if item.get("media_type") == db_media_type]
        else:
            if "latest" in id:
                sort_params = [("updated_on", "desc")]
            elif "top" in id:
                sort_params = [("rating", "desc")]
            else:
                sort_params = [("updated_on", "desc")]

            vis_filter = _merge_filters(_visibility_query(token_data), _not_exclusive_clause())
            if media_type == "movie":
                data = await db.sort_movies(sort_params, page, PAGE_SIZE, genre_filter=genre_filter, extra_filter=vis_filter)
                items = data.get("movies", [])
            else:
                data = await db.sort_tv_shows(sort_params, page, PAGE_SIZE, genre_filter=genre_filter, extra_filter=vis_filter)
                items = data.get("tv_shows", [])
    except Exception:
        return {"metas": []}

    metas = [convert_to_stremio_meta(item) for item in items]
    return {"metas": metas}


#----- Detailed metadata for a title, including series episode list
@router.get("/{token}/meta/{media_type}/{id}.json")
async def get_meta(token: str, media_type: str, id: str, token_data: dict = Depends(verify_token)):
    if SettingsManager.current().hide_catalog:
        raise HTTPException(status_code=404, detail="Catalog disabled")

    imdb_id = id

    media = await db.get_media_details(imdb_id=imdb_id, media_type=media_type)
    if not media:
        return JSONResponse(
            content={"meta": {}},
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    if not _token_can_view(media.get("visibility") or "public", media.get("allowed_tokens") or [], token_data):
        return JSONResponse(
            content={"meta": {}},
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    provider_meta: dict = {}
    provider_videos: dict[tuple[int, int], dict] = {}
    imdb_id_for_art = str(media.get("imdb_id") or id or "").strip()
    imdb_art = format_imdb_images(imdb_id_for_art)

    if media.get("media_type") == "tv":
        seasons_for_art = media.get("seasons") or []
        missing_episode_art = any(
            not _is_nonempty_url(episode.get("episode_backdrop"))
            for season in seasons_for_art
            for episode in (season.get("episodes") or [])
            if isinstance(episode, dict)
        )
        if not _is_nonempty_url(media.get("backdrop")) or missing_episode_art:
            provider_meta = await _get_provider_series_meta(imdb_id_for_art)
            provider_videos = _provider_video_map(provider_meta)

    series_poster = (
        _abs_media_url(media.get("poster"))
        or _abs_media_url(provider_meta.get("poster"))
        or imdb_art.get("poster", "")
    )
    series_backdrop = (
        _abs_media_url(media.get("backdrop"))
        or _abs_media_url(provider_meta.get("background"))
        or imdb_art.get("backdrop", "")
        or series_poster
    )
    series_logo = (
        _abs_media_url(media.get("logo"))
        or _abs_media_url(provider_meta.get("logo"))
        or imdb_art.get("logo", "")
    )

    meta_obj = {
        "id": str(id),
        "type": "series" if media.get("media_type") == "tv" else "movie",
        "name": _clean_meta_text(media.get("title"), "Unknown title"),
        "description": _clean_meta_text(media.get("description")),
        "year": str(media.get("release_year") or ""),
        "imdbRating": str(media.get("rating") or ""),
        "genres": [str(g) for g in (media.get("genres") or []) if g],
        "poster": series_poster,
        "logo": series_logo,
        "background": series_backdrop,
        "imdb_id": str(media.get("imdb_id") or id),
        "releaseInfo": str(media.get("release_year") or ""),
        "moviedb_id": str(media.get("tmdb_id") or ""),
        "cast": [str(c) for c in (media.get("cast") or []) if c],
        "runtime": _clean_meta_text(media.get("runtime")),
    }
    meta_obj = {key: value for key, value in meta_obj.items() if value not in (None, "")}

    if media.get("media_type") == "movie":
        released_date = format_released_date(media)
        if released_date:
            meta_obj["released"] = released_date

    #----- Series episodes
    if media_type == "series" and "seasons" in media:
        fallback_release = datetime.now(timezone.utc) - timedelta(days=1)
        videos = []
        seen_episodes: set[tuple[int, int]] = set()
        seasons = sorted(
            media.get("seasons", []),
            key=lambda item: int(item.get("season_number") or 0),
        )
        for season in seasons:
            try:
                season_number = int(season.get("season_number"))
            except (TypeError, ValueError):
                continue
            episodes = sorted(
                season.get("episodes", []),
                key=lambda item: int(item.get("episode_number") or 0),
            )
            for episode in episodes:
                try:
                    episode_number = int(episode.get("episode_number"))
                except (TypeError, ValueError):
                    continue
                key = (season_number, episode_number)
                if key in seen_episodes:
                    continue
                seen_episodes.add(key)

                episode_id = f"{id}:{season_number}:{episode_number}"
                provider_video = provider_videos.get(key) or {}
                episode_thumbnail = (
                    _abs_media_url(episode.get("episode_backdrop"))
                    or _abs_media_url(provider_video.get("thumbnail"))
                    or series_backdrop
                    or series_poster
                )
                video = {
                    "id": episode_id,
                    "title": _clean_meta_text(
                        episode.get("title") or provider_video.get("title"),
                        f"Episode {episode_number}",
                    ),
                    "season": season_number,
                    "episode": episode_number,
                    "overview": _clean_meta_text(
                        episode.get("overview") or provider_video.get("overview"),
                        "No description available for this episode yet.",
                    ),
                    "released": _stremio_iso_date(
                        episode.get("released") or provider_video.get("released"),
                        fallback=fallback_release,
                    ),
                    # Never return the old "Backdrop Not Available" image.
                    # For high absolute episode numbers or specials, prefer the
                    # provider still and then the series backdrop.
                    "thumbnail": episode_thumbnail,
                    "available": bool(episode.get("telegram")),
                }
                videos.append(video)
        meta_obj["videos"] = videos

    LOGGER.info(
        "[Stremio] meta response: imdb=%s type=%s videos=%s",
        imdb_id,
        media_type,
        len(meta_obj.get("videos") or []),
    )
    return JSONResponse(
        content={"meta": meta_obj},
        headers={"Cache-Control": "no-store, max-age=0"},
    )


#----- Subtitles for a title/episode, sourced from subtitle files in the channels
@router.get("/{token}/subtitles/{media_type}/{id}/{extra:path}.json")
@router.get("/{token}/subtitles/{media_type}/{id}.json")
async def get_subtitles(token: str, media_type: str, id: str, extra: Optional[str] = None, token_data: dict = Depends(verify_token)):
    try:
        parts = id.split(":")
        imdb_id = parts[0]
        season = int(parts[1]) if len(parts) > 1 else None
        episode = int(parts[2]) if len(parts) > 2 else None
    except (ValueError, IndexError):
        return {"subtitles": []}

    db_media_type = "tv" if media_type == "series" else "movie"
    subs = await get_subtitles_for(imdb_id, db_media_type, season, episode)
    if not subs:
        return {"subtitles": []}
    return {"subtitles": stremio_subtitle_entries(subs, token, SettingsManager.current().base_url)}


#----- Collect Global Search streams for a title/episode via IMDb lookup
async def _global_streams_for(token: str, imdb_id: str, media_type: str, season_num: Optional[int], episode_num: Optional[int]) -> list:
    imdb_media_type = "tvSeries" if media_type == "series" else "movie"

    detail = await get_detail(imdb_id=imdb_id, media_type=imdb_media_type)
    if not detail or not detail.get("title"):
        return []

    expected_title = detail["title"]
    year = (detail.get("releaseDetailed") or {}).get("year") or None

    if season_num is not None and episode_num is not None:
        try:
            await get_season(imdb_id=imdb_id, season_id=season_num, episode_id=episode_num)
        except Exception:
            pass

    try:
        global_results = await global_search(
            expected_title,
            SettingsManager.current().auth_channels,
            year=year,
            season=season_num,
            episode=episode_num,
        )
    except Exception as e:
        LOGGER.error(f"[GLOBAL SEARCH] search failed for '{expected_title}': {e}")
        return []

    streams = []
    for r in global_results:
        _, stream_title = format_stream_details(r["title"], r["quality"], r["size"], is_split=False)
        stream_name = f"🌐 GLOBAL {r['quality']}"
        stream_title = f"{stream_title}\n📡 {r['source_chat']}"
        url = f"{SettingsManager.current().base_url}/dl/{token}/{r['token']}/{quote(r['title'])}"
        size_bytes = parse_size_to_bytes(r.get("size", ""))
        streams.append({"name": stream_name, "title": stream_title, "url": url, "size_bytes": size_bytes})
    return streams


#----- Cached check that a user is still in the subscription group (fail-open)
async def _is_subscription_member(user_id: int) -> bool:
    group_id = SettingsManager.current().subscription_group_id
    if not group_id:
        return True

    cache_key = (group_id, user_id)
    cached = _membership_cache.get(cache_key)
    now_ts = time.monotonic()
    if cached and (now_ts - cached[0]) < _MEMBERSHIP_TTL:
        return cached[1]

    try:
        member = await StreamBot.get_chat_member(group_id, user_id)
        result = member.status not in (ChatMemberStatus.LEFT, ChatMemberStatus.BANNED)
    except UserNotParticipant:
        result = False
    except Exception as e:
        LOGGER.warning(f"[SUBSCRIPTION] Membership check failed for user {user_id}: {e}")
        return True

    if len(_membership_cache) >= _MEMBERSHIP_CACHE_MAX:
        for k in [k for k, v in _membership_cache.items() if (now_ts - v[0]) >= _MEMBERSHIP_TTL]:
            _membership_cache.pop(k, None)
        if len(_membership_cache) >= _MEMBERSHIP_CACHE_MAX:
            _membership_cache.clear()

    _membership_cache[cache_key] = (now_ts, result)
    return result


#----- Resolve playable streams for a title (Telegram library or Global Search)
@router.get("/{token}/stream/{media_type}/{id}.json")
async def get_streams(
    token: str,
    media_type: str,
    id: str,
    token_data: dict = Depends(verify_token)
):

    if token_data.get("subscription_expired"):
        return {
            "streams": [
                {
                    "name": "🚫 Plan Expired",
                    "title": "Your plan is expired.\nRenew it from the bot to continue watching.",
                    "url": get_streambot_url()
                }
            ]
        }

    #----- Subscription users must currently be members of the configured group.
    #----- Admin, lifetime and admin-set token-expiry grants skip this check.
    if (SettingsManager.current().subscription
            and not token_data.get("is_admin")
            and not token_data.get("subscription_exempt")
            and not token_data.get("expires_at")):
        user_id = token_data.get("user_id")
        if user_id and not await _is_subscription_member(int(user_id)):
            return {
                "streams": [
                    {
                        "name": "📢 Join Required",
                        "title": "First join the channel to stream it.\nThen wait for 2 min for verification",
                        "url": get_streambot_url()
                    }
                ]
            }

    if token_data.get("limit_exceeded"):
        limit_type = token_data["limit_exceeded"]

        title = (
            "🚫 Daily Limit Reached – Upgrade Required"
            if limit_type == "daily"
            else "🚫 Monthly Limit Reached – Upgrade Required"
        )

        return {
            "streams": [
                {
                    "name": "Limit Reached",
                    "title": title,
                    "url": f"tg://user?id={Telegram.OWNER_ID}"
                }
            ]
        }

    try:
        parts = id.split(":")
        imdb_id = parts[0]
        season_num = int(parts[1]) if len(parts) > 1 else None
        episode_num = int(parts[2]) if len(parts) > 2 else None
    except (ValueError, IndexError):
        raise HTTPException(status_code=400, detail="Invalid Stremio ID format")

    if not await _title_allowed(imdb_id, token_data):
        return {"streams": []}

    media_details = await db.get_media_details(
        imdb_id=imdb_id,
        season_number=season_num,
        episode_number=episode_num,
        media_type=media_type,
    )

    streams = []

    if media_details and "telegram" in media_details:
        for quality in media_details.get("telegram", []):
            if quality.get("id"):
                filename = quality.get("name", "")
                quality_str = quality.get("quality", "HD")
                size = quality.get("size", "")
                size_bytes = parse_size_to_bytes(size)

                stream_name, stream_title = format_stream_details(
                    filename, quality_str, size, is_split=bool(quality.get("group_key"))
                )

                original_url = f"{SettingsManager.current().base_url}/dl/{token}/{quality.get('id')}/video.mkv"
                proxy_url = f"{SettingsManager.current().http_proxy_url}{original_url}" if SettingsManager.current().http_proxy_url else None

                if SettingsManager.current().show_proxy_and_non_proxy_both and proxy_url:
                    streams.append({
                        "name": f"{stream_name} (Proxy)",
                        "title": stream_title,
                        "url": proxy_url,
                        "size_bytes": size_bytes
                    })
                    streams.append({
                        "name": f"{stream_name} (Direct)",
                        "title": stream_title,
                        "url": original_url,
                        "size_bytes": size_bytes
                    })
                elif proxy_url:
                    streams.append({
                        "name": stream_name,
                        "title": stream_title,
                        "url": proxy_url,
                        "size_bytes": size_bytes
                    })
                else:
                    streams.append({
                        "name": stream_name,
                        "title": stream_title,
                        "url": original_url,
                        "size_bytes": size_bytes
                    })
    elif is_global_search_enabled():
        try:
            streams.extend(
                await _global_streams_for(token, imdb_id, media_type, season_num, episode_num)
            )
        except Exception as e:
            LOGGER.error(f"[GLOBAL SEARCH] stream search failed for {imdb_id}: {e}")

    if not streams:
        LOGGER.warning(
            "[Stremio] no streams: imdb=%s type=%s season=%s episode=%s found=%s",
            imdb_id, media_type, season_num, episode_num, bool(media_details),
        )
        return JSONResponse(
            content={"streams": []},
            headers={"Cache-Control": "no-store, max-age=0"},
        )

    streams.sort(
        key=lambda s: (get_resolution_priority(s.get("name", "")), s.get("size_bytes", 0)),
        reverse=True
    )
    name_count: dict = {}
    for s in streams:
        name_count[s["name"]] = name_count.get(s["name"], 0) + 1

    seen: dict = {}
    for s in streams:
        if name_count[s["name"]] > 1:
            seen[s["name"]] = seen.get(s["name"], 0) + 1
            s["name"] = f"{s['name']} ({seen[s['name']]})"
    LOGGER.info(
        "[Stremio] stream response: imdb=%s type=%s season=%s episode=%s streams=%s",
        imdb_id, media_type, season_num, episode_num, len(streams),
    )
    return JSONResponse(
        content={"streams": streams},
        headers={"Cache-Control": "no-store, max-age=0"},
    )

#----- Configure/install landing page rendered as HTML for a token
@router.get("/{token}/configure")
async def configure_addon(token: str, request: Request):
    manifest_url = f"{SettingsManager.current().base_url}/stremio/{token}/manifest.json"
    web_install_url = f"https://web.stremio.com/#/?addon_manifest={quote(manifest_url, safe='')}"

    token_doc = await db.get_api_token(token)
    user_name = "Unknown"
    expiry_str = "N/A"
    status_color = "#ef4444"
    status_text = "Unknown"

    if token_doc:
        uid = token_doc.get("user_id")
        if uid:
            try:
                user = await db.get_user(int(uid))
                if user:
                    user_name = user.get("first_name") or user.get("username") or f"User {uid}"
                    expiry = user.get("subscription_expiry")
                    if expiry:
                        expiry_str = expiry.strftime("%d %b %Y").lstrip("0")
                    if user.get("subscription_status") == "active":
                        status_color, status_text = "#22c55e", "Active"
                    else:
                        status_color, status_text = "#ef4444", "Expired"
            except Exception:
                pass

    return templates.TemplateResponse("stremio_configure.html", {
        "request": request,
        "theme": get_theme(request.session.get("theme", DEFAULT_THEME)),
        "manifest_url": manifest_url,
        "web_install_url": web_install_url,
        "user_name": user_name,
        "expiry_str": expiry_str,
        "status_text": status_text,
        "status_color": status_color,
    })
