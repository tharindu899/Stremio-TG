import asyncio
import json
import os
import sys
from datetime import datetime
from fastapi import Request, Query, HTTPException
from fastapi.responses import FileResponse, StreamingResponse, JSONResponse
from pyrogram.enums import ChatMemberStatus, ChatMembersFilter
from pyrogram.errors import FloodWait
from pyrogram.types import ChatPrivileges
from Backend import db, StartTime, __version__
from Backend.logger import LOGGER
from Backend.helper.settings_manager import SettingsManager, get_environment_admin_credentials
from Backend.helper.pyro import get_readable_file_size, get_readable_time
from Backend.helper.metadata import (
    search_movie_candidates,
    search_tv_candidates,
    fetch_selected_movie_metadata,
    fetch_selected_tv_metadata,
)
from Backend.pyrofork.bot import multi_clients, StreamBot, Userbot
from Backend.helper.telegram_sessions import userbot_is_usable
from Backend.helper.media_mover import (
    MediaMoveError,
    start_full_media_move,
    get_full_media_move_status,
    list_full_media_move_channels,
)
from Backend.helper.custom_dl import run_speed_test, _speed_test_single_client
from time import time
from Backend.helper.auto_catalog import (
    start_auto_catalog_sync_background,
    get_auto_catalog_sync_status,
    get_auto_catalog_settings,
    update_auto_catalog_settings,
    disable_auto_catalogs,
)
from Backend.helper.tag_catalog import (
    get_catalog_tag_rule,
    get_tag_catalog_sync_status,
    start_tag_catalog_sync_background,
    update_catalog_tag_rule,
)

from Backend.helper.settings_manager import SettingsManager




# ── System & Maintenance ─────────────────────────────────────────────────────

LOG_FILE = "log.txt"


async def get_db_stats_api() -> dict:
    """Aggregate content and storage metrics across every connected storage DB."""
    try:
        total_movies = 0
        total_tv = 0
        total_episodes = 0
        total_streams = 0
        total_db_size = 0

        storage_keys = sorted(
            (key for key in db.dbs if key.startswith("storage_")),
            key=lambda key: int(key.split("_", 1)[1]),
        )

        for storage_key in storage_keys:
            storage = db.dbs.get(storage_key)
            if storage is None:
                continue

            total_movies += await storage["movie"].count_documents({})
            async for movie in storage["movie"].find({}, {"telegram": 1}):
                total_streams += len(movie.get("telegram") or [])

            total_tv += await storage["tv"].count_documents({})
            async for show in storage["tv"].find({}, {"seasons": 1}):
                for season in show.get("seasons") or []:
                    for episode in season.get("episodes") or []:
                        total_episodes += 1
                        total_streams += len(episode.get("telegram") or [])

            try:
                total_db_size += int((await storage.command("dbStats")).get("dataSize", 0))
            except Exception:
                pass

        return {
            "status": "success",
            "data": {
                "version": __version__,
                "movies": total_movies,
                "tv_shows": total_tv,
                "episodes": total_episodes,
                "streams": total_streams,
                "uptime": get_readable_time(int(time() - StartTime)),
                "db_size": get_readable_file_size(total_db_size),
                "storage_dbs": len(storage_keys),
                "auth_channels": len(SettingsManager.current().auth_channels),
            },
        }
    except Exception as exc:
        LOGGER.error(f"[Stats] Error: {exc}")
        return {"status": "error", "message": str(exc)}


async def health_api() -> dict:
    """Lightweight liveness probe used by the restart overlay."""
    return {"status": "ok", "start_time": StartTime, "version": __version__}


async def get_logs_api(lines: int = 300) -> dict:
    """Return the requested tail of the application log."""
    path = os.path.abspath(LOG_FILE)
    if not os.path.exists(path):
        return {"status": "error", "message": "Log file not found.", "log": ""}
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            tail = handle.readlines()[-max(1, min(lines, 2000)):]
        return {"status": "success", "log": "".join(tail)}
    except Exception as exc:
        return {"status": "error", "message": str(exc), "log": ""}


async def download_logs_api():
    """Download the raw application log."""
    path = os.path.abspath(LOG_FILE)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Log file not found.")
    return FileResponse(path, filename="log.txt", media_type="text/plain")


async def _perform_restart(delay: float = 1.0) -> None:
    """Run update.py, then replace this process with a fresh Backend process."""
    await asyncio.sleep(delay)
    try:
        LOGGER.info("Web-triggered restart: running updater...")
        process = await asyncio.create_subprocess_exec(sys.executable, "update.py")
        await process.wait()
        if process.returncode:
            LOGGER.warning(f"Web-triggered updater exited with code {process.returncode}.")
    except Exception as exc:
        LOGGER.error(f"Restart updater failed: {exc}")

    LOGGER.info("Web-triggered restart: re-executing app...")
    os.execl(sys.executable, sys.executable, "-m", "Backend")


async def restart_app_api() -> dict:
    asyncio.create_task(_perform_restart())
    return {
        "status": "success",
        "message": "Restart initiated — the server will be back shortly.",
    }


# --- API Routes for System Stats ---

async def get_system_stats_api():
    try:
        db_stats = await db.get_database_stats()
        total_movies = sum(stat.get("movie_count", 0) for stat in db_stats)
        total_tv_shows = sum(stat.get("tv_count", 0) for stat in db_stats)
        api_tokens = await db.get_all_api_tokens()
        
        return {
            "server_status": "running",
            "uptime": get_readable_time(time() - StartTime),
            "telegram_bot": f"@{StreamBot.username}" if StreamBot and StreamBot.username else "@StreamBot",
            "connected_bots": len(multi_clients),
            "version": __version__,
            "movies": total_movies,
            "tv_shows": total_tv_shows,
            "databases": db_stats,
            "total_databases": len(db_stats),
            "current_db_index": db.current_db_index,
            "api_tokens": api_tokens
        }
    except Exception as e:
        print(f"System Stats API Error: {e}")
        return {
            "server_status": "error", 
            "error": str(e)
        }
    
# --- API Routes for Media Management ---

async def list_media_api(
    media_type: str = Query("movie", regex="^(movie|tv)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    search: str = Query("", max_length=100)
):
    """Return Media Management cards with title-level subtitle badges.

    Subtitle availability is intentionally attached at movie/series level. It
    does not inspect individual Telegram stream qualities because one linked
    subtitle is usable for every quality of that same movie or episode.
    """
    try:
        response_key = "movies" if media_type == "movie" else "tv_shows"
        if search:
            result = await db.search_media_documents(media_type, search, page, page_size)
            result[response_key] = await db.attach_subtitle_summaries(
                result.get(response_key, []), media_type
            )
            return result

        result = (
            await db.sort_movies([], page, page_size)
            if media_type == "movie"
            else await db.sort_tv_shows([], page, page_size)
        )
        result[response_key] = await db.attach_subtitle_summaries(
            result.get(response_key, []), media_type
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def delete_media_api(
    tmdb_id: int,
    db_index: int,
    media_type: str = Query(regex="^(movie|tv)$")
):
    try:
        media_type_formatted = "Movie" if media_type == "movie" else "Series"
        result = await db.delete_document(media_type_formatted, tmdb_id, db_index)
        if result:
            return {"message": "Media deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Media not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def update_media_api(
    request: Request,
    tmdb_id: int,
    db_index: int,
    media_type: str = Query(regex="^(movie|tv)$")
):
    try:
        update_data = await request.json()
        if 'rating' in update_data and update_data['rating']:
            try:
                update_data['rating'] = float(update_data['rating'])
            except (ValueError, TypeError):
                update_data['rating'] = 0.0
        
        if 'release_year' in update_data and update_data['release_year']:
            try:
                update_data['release_year'] = int(update_data['release_year'])
            except (ValueError, TypeError):
                pass
        if 'genres' in update_data:
            if isinstance(update_data['genres'], str):
                update_data['genres'] = [g.strip() for g in update_data['genres'].split(',') if g.strip()]
            elif not isinstance(update_data['genres'], list):
                update_data['genres'] = []
        
        if 'languages' in update_data:
            if isinstance(update_data['languages'], str):
                update_data['languages'] = [l.strip() for l in update_data['languages'].split(',') if l.strip()]
            elif not isinstance(update_data['languages'], list):
                update_data['languages'] = []
        if media_type == "movie":
            if 'runtime' in update_data and update_data['runtime']:
                try:
                    update_data['runtime'] = int(update_data['runtime'])
                except (ValueError, TypeError):
                    pass
        elif media_type == "tv":
            if 'total_seasons' in update_data and update_data['total_seasons']:
                try:
                    update_data['total_seasons'] = int(update_data['total_seasons'])
                except (ValueError, TypeError):
                    pass
            
            if 'total_episodes' in update_data and update_data['total_episodes']:
                try:
                    update_data['total_episodes'] = int(update_data['total_episodes'])
                except (ValueError, TypeError):
                    pass
        update_data = {k: v for k, v in update_data.items() if v != ""}
        result = await db.update_document(media_type, tmdb_id, db_index, update_data)
        if result:
            return {"message": "Media updated successfully"}
        else:
            raise HTTPException(status_code=404, detail="Media not found or no changes made")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_media_details_api(
    tmdb_id: int,
    db_index: int,
    media_type: str = Query(regex="^(movie|tv)$")
):
    try:
        result = await db.get_document(media_type, tmdb_id, db_index)
        if result:
            return result
        else:
            raise HTTPException(status_code=404, detail="Media not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def media_title_move_channels_api(tmdb_id: int, db_index: int, media_type: str):
    normalized_type = str(media_type or "").strip().lower()
    if normalized_type not in {"movie", "tv", "series"}:
        raise HTTPException(status_code=400, detail="media_type must be movie or tv.")
    try:
        channels = await list_full_media_move_channels(
            db,
            tmdb_id=int(tmdb_id),
            db_index=int(db_index),
            media_type=normalized_type,
        )
        return {"status": "success", "data": channels}
    except MediaMoveError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        LOGGER.exception("[MediaMove] Could not load title destinations: %s", exc)
        raise HTTPException(status_code=500, detail="Could not load available move destinations.")


async def start_media_title_move_api(
    request: Request, tmdb_id: int, db_index: int, media_type: str
):
    normalized_type = str(media_type or "").strip().lower()
    if normalized_type not in {"movie", "tv", "series"}:
        raise HTTPException(status_code=400, detail="media_type must be movie or tv.")

    try:
        payload = await request.json()
    except Exception:
        payload = {}
    target_channel = str(payload.get("target_channel") or "").strip()
    if not target_channel:
        raise HTTPException(status_code=400, detail="Choose a destination channel.")

    try:
        return await start_full_media_move(
            db,
            tmdb_id=int(tmdb_id),
            db_index=int(db_index),
            media_type=normalized_type,
            target_channel=target_channel,
        )
    except MediaMoveError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except Exception as exc:
        LOGGER.exception("[MediaMove] Could not start full-title move: %s", exc)
        raise HTTPException(status_code=500, detail="Could not start the full-title move.")


async def media_title_move_status_api(job_id: str):
    try:
        payload = get_full_media_move_status(job_id)
        return JSONResponse(
            payload,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
            },
        )
    except MediaMoveError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


async def delete_movie_quality_api(tmdb_id: int, db_index: int, id: str):
    try:
        result = await db.delete_movie_quality(tmdb_id, db_index, id)
        if result:
            return {"message": "Quality deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Quality not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def delete_tv_quality_api(
    tmdb_id: int, db_index: int, season: int, episode: int, id: str
):
    try:
        result = await db.delete_tv_quality(tmdb_id, db_index, season, episode, id)
        if result:
            return {"message": "deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Quality not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def delete_tv_episode_api(
    tmdb_id: int, db_index: int, season: int, episode: int
):
    try:
        result = await db.delete_tv_episode(tmdb_id, db_index, season, episode)
        if result:
            return {"message": "Episode deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Episode not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def delete_tv_season_api(tmdb_id: int, db_index: int, season: int):
    try:
        result = await db.delete_tv_season(tmdb_id, db_index, season)
        if result:
            return {"message": "Season deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Season not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- API Routes for Token Management ---

async def create_token_api(payload: dict):
    try:
        token_name = payload.get("name")
        daily_limit = payload.get("daily_limit_gb")
        monthly_limit = payload.get("monthly_limit_gb")
        
        if not token_name:
             raise HTTPException(status_code=400, detail="Token name is required")
        def parse_limit(val):
            try:
                v = float(val)
                return v if v > 0 else None
            except (ValueError, TypeError):
                return None

        new_token = await db.add_api_token(
            token_name, 
            parse_limit(daily_limit), 
            parse_limit(monthly_limit)
        )
        return new_token
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def update_token_limits_api(token: str, payload: dict):
    try:
        daily_limit = payload.get("daily_limit_gb")
        monthly_limit = payload.get("monthly_limit_gb")
        
        def parse_limit(val):
            try:
                v = float(val)
                return v if v > 0 else None
            except (ValueError, TypeError, AttributeError):
                return None

        result = await db.update_api_token_limits(
            token,
            parse_limit(daily_limit),
            parse_limit(monthly_limit)
        )
        
        if result:
            return {"message": "Limits updated successfully"}
        else:
            return {"message": "Limits updated successfully"}
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def revoke_token_api(token: str):
    try:
        result = await db.revoke_api_token(token)
        if result:
            return {"message": "Token revoked successfully"}
        else:
            raise HTTPException(status_code=404, detail="Token not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Speed Test API ---

def _normalise_speedtest_chat_id(raw_chat_id) -> int:
    """Return a Telegram channel id in ``-100...`` format."""
    value = str(raw_chat_id or "").strip()
    if not value:
        raise ValueError("Missing Telegram channel id")
    if value.startswith("-100"):
        return int(value)
    if value.startswith("-"):
        return int(value)
    return int(f"-100{value}")


def _resolve_speedtest_target(decoded: dict) -> dict:
    """Resolve a normal or virtual split quality payload for a speed test.

    A virtual split stream has no top-level ``msg_id``.  Speed testing every
    split part would multiply the normal 100 MB diagnostic transfer, so we
    sample the first ordered part.  All split parts use the same source
    channel and this measures the actual Telegram delivery path without
    consuming several hundred MB per connected bot.
    """
    if not isinstance(decoded, dict):
        raise ValueError("Decoded quality payload is invalid")

    parts = decoded.get("parts")
    if isinstance(parts, list) and parts:
        valid_parts = [
            part for part in parts
            if isinstance(part, dict) and part.get("chat_id") is not None and part.get("msg_id") is not None
        ]
        if not valid_parts:
            raise ValueError("Split stream has no valid Telegram parts")
        sample = valid_parts[0]
        return {
            "chat_id": _normalise_speedtest_chat_id(sample.get("chat_id")),
            "msg_id": int(sample.get("msg_id")),
            "split_parts": len(valid_parts),
            "sample_part": 1,
        }

    raw_chat_id = decoded.get("chat_id")
    msg_id = decoded.get("msg_id")
    if raw_chat_id is None or msg_id is None:
        raise ValueError("Decoded quality data is missing msg_id or chat_id")
    return {
        "chat_id": _normalise_speedtest_chat_id(raw_chat_id),
        "msg_id": int(msg_id),
        "split_parts": 1,
        "sample_part": 1,
    }


async def speed_test_api(
    quality_id: str = Query(..., description="Encoded quality ID from DB"),
    tmdb_id: int = Query(...),
    db_index: int = Query(...),
    media_type: str = Query(..., regex="^(movie|tv)$"),
):
    """
    Decode quality_id using the same decode_string logic as the stream handler,
    then run a parallel download speed test across all connected bot clients.
    """
    from Backend.helper.encrypt import decode_string

    try:
        decoded = await decode_string(quality_id)
        target = _resolve_speedtest_target(decoded)

        if target["split_parts"] > 1:
            LOGGER.info(
                "[SpeedTest] split stream: sampling part %s/%s (chat=%s msg=%s)",
                target["sample_part"], target["split_parts"], target["chat_id"], target["msg_id"],
            )

        results = await run_speed_test(target["chat_id"], target["msg_id"])
        return {
            "results": results,
            "total_clients_tested": len(results),
            "split_parts": target["split_parts"],
            "sample_part": target["sample_part"],
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Speed Test SSE Streaming API ---

async def speed_test_stream_api(
    quality_id: str,
    tmdb_id: int,
    db_index: int,
    media_type: str,
):
    """
    SSE version of the speed test. Streams each per-client result as a
    'data:' event the moment that client finishes, so the UI can update live.
    """
    from Backend.helper.encrypt import decode_string

    async def event_generator():
        # Decode a normal quality id or resolve the first sample part from a
        # virtual split stream.  Testing one part avoids a 100 MB transfer for
        # every member of the split set while still measuring the same Telegram path.
        try:
            decoded = await decode_string(quality_id)
            target = _resolve_speedtest_target(decoded)
            chat_id = target["chat_id"]
            msg_id = target["msg_id"]
            split_parts = target["split_parts"]
            sample_part = target["sample_part"]
            if split_parts > 1:
                LOGGER.info(
                    "[SpeedTest] split stream: sampling part %s/%s (chat=%s msg=%s)",
                    sample_part, split_parts, chat_id, msg_id,
                )
        except Exception as exc:
            payload = json.dumps({"type": "error", "message": f"Cannot resolve stream for speed test: {exc}"})
            yield f"data: {payload}\n\n"
            return

        total = len(multi_clients)
        if total == 0:
            payload = json.dumps({"type": "error", "message": "No bot clients connected"})
            yield f"data: {payload}\n\n"
            return
            
        # Try to resolve the FileId to get the target DC
        target_dc = "?"
        try:
            from Backend.helper.custom_dl import ByteStreamer
            primary_client = multi_clients.get(0) or next(iter(multi_clients.values()))
            streamer = ByteStreamer(primary_client)
            file_id = await streamer.get_file_properties(chat_id, int(msg_id))
            target_dc = file_id.dc_id
        except Exception:
            pass

        # Send initial "start" event so the frontend can set up the table.
        # Build JSON first: multiline expressions inside an f-string are invalid
        # on older Python parsers and previously stopped the app at startup.
        start_payload = json.dumps({
            "type": "start",
            "total": total,
            "target_dc": target_dc,
            "split_parts": split_parts,
            "sample_part": sample_part,
        })
        yield f"data: {start_payload}\n\n"

        # Run all clients in parallel; feed results into a queue as they finish
        queue: asyncio.Queue = asyncio.Queue()

        async def run_one(client, idx):
            async def on_progress(prog_data):
                await queue.put({"type": "progress", "data": prog_data})
                
            result = await _speed_test_single_client(
                client, idx, chat_id, int(msg_id), progress_callback=on_progress
            )
            await queue.put({"type": "result", "data": result})

        tasks = [
            asyncio.create_task(run_one(client, idx))
            for idx, client in multi_clients.items()
        ]

        completed = 0
        while completed < total:
            msg = await queue.get()
            
            if msg["type"] == "progress":
                payload = json.dumps(msg)
                yield f"data: {payload}\n\n"
            
            elif msg["type"] == "result":
                completed += 1
                payload = json.dumps({
                    "type": "result",
                    "data": msg["data"],
                    "completed": completed,
                    "total": total,
                })
                yield f"data: {payload}\n\n"

        # Wait for any remaining tasks (should already be done)
        await asyncio.gather(*tasks, return_exceptions=True)

        # Final done event
        yield f"data: {json.dumps({'type': 'done', 'total': total})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # prevent nginx from buffering SSE
        },
    )

# ---------------------------------------------------------------------------
# Admin API Routes
# ---------------------------------------------------------------------------

async def get_admin_stats_api() -> dict:
    from Backend.pyrofork.bot import work_loads, multi_clients, client_failures, client_avg_mbps
    from Backend.fastapi.routes.stream_routes import _streamer_by_client
    
    # Sum cache entries across all active ByteStreamer instances
    cache_size = sum(len(s._file_id_cache) for s in _streamer_by_client.values())
    
    # Calculate bot workloads and health
    bot_stats = []
    for client_index in multi_clients:
        load = work_loads.get(client_index, 0)
        failures = client_failures.get(client_index, 0)
        mbps = client_avg_mbps.get(client_index, 0.0)
        
        status = "healthy"
        if failures > 5:
            status = "degraded"
        if failures > 15:
            status = "failing"
            
        bot_stats.append({
            "client_index": client_index,
            "display_name": f"Bot {client_index + 1}",
            "current_load": load,
            "failures": failures,
            "avg_mbps": round(mbps, 2),
            "status": status
        })
        
    return {
        "cache_size": cache_size,
        "total_bots": len(multi_clients),
        "bot_workloads": bot_stats
    }

async def clear_cache_api() -> dict:
    from Backend.fastapi.routes.stream_routes import _streamer_by_client
    from Backend.logger import LOGGER
    
    # Clear cache across all active ByteStreamer instances
    total_cleared = sum(len(s._file_id_cache) for s in _streamer_by_client.values())
    for streamer in _streamer_by_client.values():
        streamer._file_id_cache.clear()
    LOGGER.info(f"Admin cleared the FileId cache ({total_cleared} items purged across {len(_streamer_by_client)} clients).")
    
    return {"status": "success", "message": f"{total_cleared} cached items cleared."}

async def get_dead_links_api() -> dict:
    from Backend import db
    try:
        dead_links = await db.get_all_dead_links()
        return {"status": "success", "data": dead_links}
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def get_stream_analytics_api() -> dict:
    from Backend import db
    try:
        data = await db.get_stream_analytics(limit=200)
        return {"status": "success", "data": data}
    except Exception as e:
        from Backend.logger import LOGGER
        LOGGER.error(f"Stream analytics API error: {e}")
        return {"status": "error", "message": str(e)}

async def clear_stream_analytics_api() -> dict:
    try:
        result = await db.dbs["tracking"]["stream_analytics"].delete_many({})
        LOGGER.info(f"Admin cleared stream analytics ({result.deleted_count} records deleted).")

        return {
            "status": "success",
            "message": f"{result.deleted_count} analytics records cleared."
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}

# ---------------------------------------------------------------------------
# Admin Subscription Management API Routes
# ---------------------------------------------------------------------------

async def get_subscription_plans_api() -> dict:
    from Backend import db
    try:
        plans = await db.get_subscription_plans()
        return {"status": "success", "data": plans}
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def add_subscription_plan_api(payload: dict) -> dict:
    from Backend import db
    try:
        days = int(payload.get("days", 0))
        price = float(payload.get("price", 0.0))
        if days <= 0 or price < 0:
            raise HTTPException(status_code=400, detail="Invalid plan parameters")
            
        plan_id = await db.add_subscription_plan(days, price)
        if plan_id:
            return {"status": "success", "message": "Plan added successfully", "plan_id": plan_id}
        else:
            raise HTTPException(status_code=500, detail="Failed to add plan")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def update_subscription_plan_api(plan_id: str, payload: dict) -> dict:
    from Backend import db
    try:
        days = int(payload.get("days", 0))
        price = float(payload.get("price", 0.0))
        if days <= 0 or price < 0:
             raise HTTPException(status_code=400, detail="Invalid plan parameters")
             
        success = await db.update_subscription_plan(plan_id, days, price)
        if success:
             return {"status": "success", "message": "Plan updated successfully"}
        else:
             raise HTTPException(status_code=404, detail="Plan not found or update failed")
    except HTTPException:
         raise
    except Exception as e:
         raise HTTPException(status_code=500, detail=str(e))

async def delete_subscription_plan_api(plan_id: str) -> dict:
    from Backend import db
    try:
        success = await db.delete_subscription_plan(plan_id)
        if success:
            return {"status": "success", "message": "Plan deleted successfully"}
        else:
            raise HTTPException(status_code=404, detail="Plan not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

async def get_all_subscribers_api() -> dict:
    from Backend import db
    try:
        users = await db.get_all_subscribers()
        return {"status": "success", "data": users}
    except Exception as e:
        return {"status": "error", "message": str(e)}

async def manage_subscriber_api(user_id: int, payload: dict) -> dict:
    from Backend import db
    try:
        action = payload.get("action")
        days = int(payload.get("days", 0))
        
        if action not in ["extend", "reduce", "delete"]:
            raise HTTPException(status_code=400, detail="Invalid action")
            
        success = await db.manage_subscriber(user_id, action, days)
        if success:
            return {"status": "success", "message": "User subscription updated successfully"}
        else:
            raise HTTPException(status_code=404, detail="User not found or update failed")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Access Management API ---

async def get_all_tokens_api() -> dict:
    try:
        tokens = await db.get_all_api_tokens()
        now = datetime.utcnow()
        result = []

        # Pre-load all subscribers into a dict keyed by user_id for O(1) lookup
        subscriber_map = {}       # user_id (str) -> user doc
        if SettingsManager.current().subscription:
            try:
                for u in await db.get_all_subscribers():
                    uid = str(u.get("_id"))
                    subscriber_map[uid] = u
            except Exception:
                pass

        def display_name(user, user_id, token_name=None):
            """Return a non-empty display name for a user."""
            if user:
                n = user.get("first_name") or user.get("username")
                if n:
                    return n
            # Fall back to the name stored on the token itself (set at creation time)
            if token_name:
                return token_name
            return f"User {user_id}" if user_id else "Telegram User"

        def build_entry(user_id, user, token_doc):
            """ a unified access entry from optional user + token records."""
            expiry = None
            sub_status = None
            user_found = bool(user)

            if user:
                sub_status = user.get("subscription_status")
                expiry = user.get("subscription_expiry")

            # Token-level expiry as fallback
            if token_doc:
                t_expiry = token_doc.get("subscription_expiry") or token_doc.get("expires_at")
                if t_expiry and not expiry:
                    expiry = t_expiry

            # Determine status
            if SettingsManager.current().subscription:
                if not user_found:
                    is_expired = True
                elif sub_status != "active":
                    is_expired = True
                elif not expiry:
                    is_expired = True
                else:
                    is_expired = expiry < now
            else:
                is_expired = bool(expiry and expiry < now)

            token_str = token_doc.get("token") if token_doc else None
            created = token_doc.get("created_at") if token_doc else (user.get("created_at") if user else None)

            return {
                "token": token_str,
                "user_id": user_id,
                "user_name": display_name(user, user_id, token_doc.get("name") if token_doc else None),
                "user_found": user_found,
                "has_token": bool(token_str),
                "created_at": created.isoformat() if created else None,
                "expires_at": expiry.isoformat() if expiry else None,
                "is_expired": is_expired,
                "sub_status": sub_status,
                "addon_url": (
                    f"{SettingsManager.current().base_url}/stremio/{token_str}/manifest.json"
                    if token_str else None
                ),
            }

        # Track user_ids that are already represented via a token row
        seen_user_ids = set()

        # --- 1. Process all existing tokens ---
        for t in tokens:
            token_user_id = t.get("user_id")

            # Try to resolve user from subscriber_map using token's user_id
            user = None
            if token_user_id:
                uid_str = str(token_user_id)
                user = subscriber_map.get(uid_str)
                if not user:
                    # Fallback: query DB if not in subscriber_map (e.g. non-active subscribers)
                    try:
                        user = await db.get_user(int(token_user_id))
                    except Exception:
                        pass
                seen_user_ids.add(uid_str)

            result.append(build_entry(token_user_id, user, t))

        # --- 2. Add subscribers who have NO token ---
        for uid_str, u in subscriber_map.items():
            if uid_str in seen_user_ids:
                continue  # already covered by a token row
            result.append(build_entry(u.get("_id"), u, None))

        # Sort: active-with-token first, then active-no-token, expired last
        result.sort(key=lambda x: (x["is_expired"], not x["has_token"]))
        return {"tokens": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def revoke_token_api(token: str) -> dict:
    from Backend import db
    try:
        success = await db.revoke_api_token(token)
        if success:
            return {"status": "success", "message": "Token revoked."}
        raise HTTPException(status_code=404, detail="Token not found.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def assign_plan_api(user_id: int, days: int) -> dict:
    """Assign (or extend) a subscription for any user by user_id, even if not in DB."""
    from Backend import db
    try:
        if days < 1:
            raise HTTPException(status_code=400, detail="Days must be at least 1.")
        result = await db.assign_subscription(user_id, days)
        return {"status": "success", "data": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def link_token_user_api(token: str, user_id: int) -> dict:
    """Link an orphan token (no user_id) to a Telegram user_id."""
    from Backend import db
    try:
        success = await db.link_token_user(token, user_id)
        if success:
            return {"status": "success", "message": f"Token linked to user {user_id}."}
        raise HTTPException(status_code=404, detail="Token not found or already linked.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




async def search_media_rescan_api(media_type: str, query: str, year: int | None = None):
    query = (query or "").strip()
    if not query:
        raise HTTPException(status_code=400, detail="query is required.")

    if media_type == "movie":
        results = await search_movie_candidates(query=query, year=year)
    elif media_type == "tv":
        results = await search_tv_candidates(query=query)
    else:
        raise HTTPException(status_code=400, detail="Invalid media_type.")

    return {"results": results}


async def apply_media_rescan_api(request: Request, tmdb_id: int, db_index: int, media_type: str):
    body = await request.json()
    selected_id = str(body.get("selected_id") or "").strip()

    if not selected_id:
        raise HTTPException(status_code=400, detail="selected_id is required.")

    current_doc = await db.get_document(media_type, tmdb_id, db_index)
    if not current_doc:
        raise HTTPException(status_code=404, detail="Media not found.")

    if media_type == "movie":
        metadata = await fetch_selected_movie_metadata(selected_id)
    elif media_type == "tv":
        metadata = await fetch_selected_tv_metadata(selected_id)
    else:
        raise HTTPException(status_code=400, detail="Invalid media_type.")

    if not metadata:
        raise HTTPException(status_code=404, detail="Unable to fetch metadata for selected item.")

    updated_doc = await db.replace_media_metadata(
        media_type=media_type,
        tmdb_id=tmdb_id,
        db_index=db_index,
        metadata=metadata,
    )

    if not updated_doc:
        raise HTTPException(status_code=500, detail="Failed to replace media metadata.")

    return {
        "success": True,
        "message": "Metadata rescanned successfully.",
        "redirect_tmdb_id": updated_doc.get("tmdb_id"),
        "db_index": updated_doc.get("db_index", db_index),
        "media_type": media_type,
        "data": updated_doc,
}


# --- Custom Catalog APIs ---

def _normalize_media_type(media_type: str) -> str:
    return "tv" if media_type in ["tv", "series"] else "movie"


async def list_custom_catalogs_api(
    tmdb_id: int | None = None,
    db_index: int | None = None,
    media_type: str | None = None,
):
    try:
        catalogs = await db.get_custom_catalogs()
        if tmdb_id is not None and db_index is not None and media_type:
            normalized_type = _normalize_media_type(media_type)
            for catalog in catalogs:
                catalog["contains_current"] = any(
                    int(item.get("tmdb_id", -1)) == int(tmdb_id)
                    and int(item.get("db_index", -1)) == int(db_index)
                    and item.get("media_type") == normalized_type
                    for item in catalog.get("items", []) or []
                )
        return {"catalogs": catalogs}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def create_custom_catalog_api(payload: dict):
    name = (payload.get("name") or "").strip()
    visible = bool(payload.get("visible", True))
    if not name:
        raise HTTPException(status_code=400, detail="Catalog name is required.")

    catalog_id = await db.create_custom_catalog(name=name, visible=visible)
    if not catalog_id:
        raise HTTPException(status_code=500, detail="Failed to create catalog.")

    catalog = await db.get_custom_catalog(catalog_id)
    return {"message": "Catalog created successfully.", "catalog": catalog}


async def update_custom_catalog_api(catalog_id: str, payload: dict):
    name = payload.get("name")
    visible = payload.get("visible") if "visible" in payload else None
    result = await db.update_custom_catalog(catalog_id, name=name, visible=visible)
    if not result:
        catalog = await db.get_custom_catalog(catalog_id)
        if not catalog:
            raise HTTPException(status_code=404, detail="Catalog not found.")
    return {"message": "Catalog updated successfully.", "catalog": await db.get_custom_catalog(catalog_id)}


async def delete_custom_catalog_api(catalog_id: str):
    result = await db.delete_custom_catalog(catalog_id)
    if not result:
        raise HTTPException(status_code=404, detail="Catalog not found.")
    return {"message": "Catalog deleted successfully."}


async def get_custom_catalog_items_api(
    catalog_id: str,
    media_type: str | None = None,
    page: int = 1,
    page_size: int = 24,
):
    try:
        data = await db.get_custom_catalog_items(catalog_id, media_type, page, page_size)
        if not data.get("catalog"):
            raise HTTPException(status_code=404, detail="Catalog not found.")
        return data
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def search_catalog_media_api(
    query: str,
    media_type: str = "movie",
    page: int = 1,
    page_size: int = 12,
):
    query = (query or "").strip()
    if not query:
        return {"results": [], "total_count": 0}

    try:
        result = await db.search_documents(query, page, page_size)
        normalized_type = _normalize_media_type(media_type)
        filtered = [item for item in result.get("results", []) if item.get("media_type") == normalized_type]
        return {"results": filtered, "total_count": len(filtered)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def add_custom_catalog_item_api(catalog_id: str, payload: dict):
    tmdb_id = payload.get("tmdb_id")
    db_index = payload.get("db_index")
    media_type = _normalize_media_type(payload.get("media_type", "movie"))

    if not tmdb_id or not db_index:
        raise HTTPException(status_code=400, detail="tmdb_id and db_index are required.")

    media = await db.get_document(media_type, int(tmdb_id), int(db_index))
    if not media:
        raise HTTPException(status_code=404, detail="Media not found.")

    catalog = await db.get_custom_catalog(catalog_id)
    if not catalog:
        raise HTTPException(status_code=404, detail="Catalog not found.")

    added = await db.add_item_to_custom_catalog(catalog_id, int(tmdb_id), int(db_index), media_type)
    message = "Added to catalog." if added else "Already exists in this catalog."
    return {"message": message, "added": added}


async def remove_custom_catalog_item_api(
    catalog_id: str,
    tmdb_id: int,
    db_index: int,
    media_type: str,
):
    catalog = await db.get_custom_catalog(catalog_id)
    if not catalog:
        raise HTTPException(status_code=404, detail="Catalog not found.")

    removed = await db.remove_item_from_custom_catalog(
        catalog_id, int(tmdb_id), int(db_index), _normalize_media_type(media_type)
    )
    if not removed:
        return {"message": "Item was not in this catalog.", "removed": False}
    return {"message": "Removed from catalog.", "removed": True}


async def get_custom_catalog_tag_rule_api(catalog_id: str):
    rule = await get_catalog_tag_rule(db, catalog_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Catalog not found.")
    if not rule.get("available"):
        raise HTTPException(status_code=400, detail="TMDb automatic catalogs manage their own items and cannot use caption tag rules.")
    return rule


async def update_custom_catalog_tag_rule_api(catalog_id: str, payload: dict):
    tags = payload.get("tags", [])
    enabled = payload.get("enabled", True)
    if not isinstance(tags, (str, list)):
        raise HTTPException(status_code=400, detail="tags must be a list or comma-separated text.")
    rule = await update_catalog_tag_rule(db, catalog_id, tags, enabled)
    if not rule:
        raise HTTPException(status_code=404, detail="Catalog not found or is managed automatically.")
    sync = await start_tag_catalog_sync_background(db, force=True)
    return {
        "message": "Caption tag rule saved. Matching titles are updating in the background.",
        "rule": rule,
        "sync": sync,
    }


async def sync_custom_catalog_tag_rules_api():
    try:
        result = await start_tag_catalog_sync_background(db, force=True)
        return {"message": result.get("message", "Caption tag sync started."), "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def custom_catalog_tag_sync_status_api():
    try:
        return {"status": await get_tag_catalog_sync_status(db)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def auto_sync_custom_catalogs_api(full_rebuild: bool = False):
    try:
        result = await start_auto_catalog_sync_background(db, force=True, full_rebuild=full_rebuild)
        return {"message": result.get("message", "Auto sync started."), "result": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def auto_catalog_sync_status_api():
    try:
        settings = await get_auto_catalog_settings(db)
        return {
            "status": await get_auto_catalog_sync_status(db),
            "settings": {
                "configured": settings.get("configured", False),
                "enabled_keys": settings.get("enabled_keys", []),
                "revision": settings.get("revision", 0),
            },
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def get_auto_catalog_settings_api():
    try:
        return {"settings": await get_auto_catalog_settings(db)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


async def update_auto_catalog_settings_api(payload: dict):
    try:
        enabled_keys = payload.get("enabled_keys", [])
        if not isinstance(enabled_keys, list):
            raise HTTPException(status_code=400, detail="enabled_keys must be a list.")

        settings = await update_auto_catalog_settings(db, enabled_keys)
        selected = settings.get("enabled_keys", [])
        sync = None

        if not selected:
            await disable_auto_catalogs(db)
            message = "Choices saved. Automatic catalogs are disabled until you select a category."
        elif settings.get("changed"):
            # Saving a changed selection immediately starts a revision-aware
            # Quick Sync. Existing media is reclassified in the background.
            sync = await start_auto_catalog_sync_background(db, force=True, full_rebuild=False)
            message = "Choices saved. Catalog sync started in the background."
        else:
            message = "Choices are already saved. Use Quick Sync when new media arrives."

        return {"message": message, "settings": settings, "sync": sync}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))




# ─────────────────────────────────────────────────────────────────────────────
# Settings API
# ─────────────────────────────────────────────────────────────────────────────

async def get_settings_api() -> dict:

    data = SettingsManager.current().to_dict()
    # Never expose the raw password — let the UI know whether one is set
    data["admin_password_set"] = bool(data.get("admin_password"))
    data["admin_password"] = ""
    data["mediaflow_password_set"] = bool(data.get("mediaflow_password"))
    data["mediaflow_password"] = ""
    data["admin_credentials_source"] = (
        "environment" if get_environment_admin_credentials() else "database"
    )

    try:
        data["database_list"] = db.get_database_list()
    except Exception as e:
        LOGGER.error(f"get_settings_api: could not load database list: {e}")
        data["database_list"] = []

    return {"settings": data}


async def update_settings_api(payload: dict) -> dict:

    # Empty password string → don't change it
    if "admin_password" in payload and not str(payload["admin_password"]).strip():
        del payload["admin_password"]
    if "mediaflow_password" in payload and not str(payload["mediaflow_password"]).strip():
        del payload["mediaflow_password"]

    # The Settings page saves one full form. A stale or partially loaded browser
    # must not erase working API/base URL values with empty inputs. Clearing one
    # of these deliberate runtime values now requires a dedicated future action.
    preserved_empty_fields = {
        "tmdb_api", "base_url", "upstream_repo", "upstream_branch",
        "http_proxy_url", "subscription_url", "payment_instructions", "payment_qr_url",
    }
    preserved = []
    current_settings = SettingsManager.current().to_dict()
    for key in preserved_empty_fields:
        if key in payload and isinstance(payload[key], str) and not payload[key].strip() and current_settings.get(key):
            payload.pop(key)
            preserved.append(key)

    # ── Type coercion & validation ────────────────────────────────────────────
    bool_keys = {
        "replace_mode", "hide_catalog", "subscription",
        "show_proxy_and_non_proxy_both", "mediaflow_proxy", "upload_status_messages",
    }
    for key in bool_keys:
        if key in payload:
            payload[key] = bool(payload[key])

    list_str_keys = {"auth_channels", "multi_tokens", "extra_databases", "global_search_channels"}
    for key in list_str_keys:
        if key in payload:
            if not isinstance(payload[key], list):
                raise HTTPException(status_code=400, detail=f"'{key}' must be a list.")
            payload[key] = [str(v).strip() for v in payload[key] if str(v).strip()]

    if "better_poster" in payload:
        payload["better_poster"] = str(payload["better_poster"] or "").strip()
        if payload["better_poster"] and "{imdb_id}" not in payload["better_poster"]:
            raise HTTPException(
                status_code=400,
                detail="Better Poster URL must contain the {imdb_id} placeholder.",
            )

    if "extra_databases" in payload:
        for uri in payload["extra_databases"]:
            if not uri.startswith(("mongodb://", "mongodb+srv://")):
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid database URI (must start with mongodb:// or mongodb+srv://): {uri[:30]}…"
                )

    if "approver_ids" in payload:
        if not isinstance(payload["approver_ids"], list):
            raise HTTPException(status_code=400, detail="'approver_ids' must be a list.")
        try:
            payload["approver_ids"] = [int(v) for v in payload["approver_ids"] if str(v).strip()]
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="All approver_ids must be integers.")

    if "subscription_group_id" in payload:
        try:
            payload["subscription_group_id"] = int(payload["subscription_group_id"])
        except (ValueError, TypeError):
            raise HTTPException(status_code=400, detail="'subscription_group_id' must be an integer.")
    if "global_search_channels" in payload:
        cleaned = []
        for channel in payload["global_search_channels"]:
            channel = str(channel).strip()
            if not channel:
                continue
            try:
                int(channel)
            except ValueError:
                raise HTTPException(status_code=400,
                    detail=f"Invalid channel id: {channel}"
                    )
            cleaned.append(channel)
        payload["global_search_channels"] = cleaned

    # Strip whitespace from string fields
    for key in ("tmdb_api", "base_url", "upstream_repo", "upstream_branch",
                "admin_username", "admin_password", "http_proxy_url", "mediaflow_password", "subscription_url",
                "payment_instructions", "payment_qr_url"):
        if key in payload and isinstance(payload[key], str):
            payload[key] = payload[key].strip()

    try:
        reinit_results = await SettingsManager.update(db, payload)
        saved = SettingsManager.current()
        return {
            "message": "Settings saved and verified in MongoDB.",
            "reinit": reinit_results,
            "preserved_empty_fields": preserved,
            "persistence": {
                "revision": saved.to_dict().get("settings_revision", 0),
                "tmdb_api_configured": bool(saved.tmdb_api),
                "base_url": saved.base_url,
                "updated_at": saved.to_dict().get("updated_at", ""),
            },
        }
    except ValueError as exc:
        # Raised by db.reload_extra_databases() for unsafe/invalid DB changes
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))



# ─────────────────────────────────────────────────────────────────────────────
#  Tools — WebUI replacement for /scan, /rescan, /scanstatus, /cancelscan,
#  /dbcheck. All driven from the Tools page; no bot commands remain.
# ─────────────────────────────────────────────────────────────────────────────

def _scan_client():
    """Pick the admin bot that fetches explicit channel message IDs."""
    if StreamBot is not None:
        return StreamBot
    if multi_clients:
        return multi_clients.get(0) or next(iter(multi_clients.values()))
    return None


def _scan_history_client():
    """Return a real user session for GetHistory when one is configured.

    Telegram rejects messages.GetHistory for bot accounts.  The scanner still
    reads message IDs through the admin bot; this optional session is used only
    to learn the exact channel tail for progress and cursor safety.
    """
    if not userbot_is_usable(Userbot):
        return None
    me = getattr(Userbot, "me", None)
    if me is not None and getattr(me, "is_bot", False):
        return None
    return Userbot


async def get_tools_channels_api() -> dict:
    """Return the configured AUTH channels with friendly names for the picker."""
    channels = list(SettingsManager.current().auth_channels)
    client = _scan_client()
    result = []
    for ch in channels:
        name = str(ch)
        try:
            if client is not None:
                chat = await client.get_chat(int(ch) if str(ch).lstrip("-").isdigit() else ch)
                name = getattr(chat, "title", None) or getattr(chat, "first_name", None) or str(ch)
        except Exception as e:
            LOGGER.warning(f"[Tools] Could not resolve channel {ch}: {e}")
        result.append({"id": str(ch), "name": name})
    return {"status": "success", "data": result}


async def start_scan_api(payload: dict) -> dict:
    """Start the single channel scanner with a media/subtitle scope."""
    from Backend.helper.scan_manager import scan_manager

    client = _scan_client()
    if client is None:
        raise HTTPException(status_code=503, detail="No Telegram client is connected yet.")

    mode = str(payload.get("mode", "scan")).lower()
    if mode not in ("scan", "rescan"):
        raise HTTPException(status_code=400, detail="mode must be 'scan' or 'rescan'.")
    scope = str(payload.get("scope", "all")).strip().lower()
    if scope not in {"media", "subtitles", "all"}:
        raise HTTPException(status_code=400, detail="scope must be 'media', 'subtitles', or 'all'.")
    channels = payload.get("channels") or []
    if not isinstance(channels, list):
        raise HTTPException(status_code=400, detail="'channels' must be a list.")

    result = await scan_manager.start(
        client,
        channels,
        mode=mode,
        content_scope=scope,
        history_client=_scan_history_client(),
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("message", "Could not start scan."))
    return {"status": "success", **result}


async def cancel_scan_api() -> dict:
    from Backend.helper.scan_manager import scan_manager
    result = await scan_manager.cancel()
    return {"status": "success" if result.get("ok") else "error", **result}


async def scan_status_api() -> dict:
    from Backend.helper.scan_manager import scan_manager
    return {"status": "success", "data": scan_manager.get_status()}


async def start_dbcheck_api() -> dict:
    from Backend.helper.scan_manager import dbcheck_manager
    # A real user session can read all stored source posts and avoids false
    # dead-link flags when the bot cannot access a message authored by someone else.
    client = _scan_history_client() or _scan_client()
    if client is None:
        raise HTTPException(status_code=503, detail="No Telegram client is connected yet.")
    result = await dbcheck_manager.start(client)
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("message", "Could not start DB check."))
    return {"status": "success", **result}


async def cancel_dbcheck_api() -> dict:
    from Backend.helper.scan_manager import dbcheck_manager
    result = await dbcheck_manager.cancel()
    return {"status": "success" if result.get("ok") else "error", **result}


async def dbcheck_status_api() -> dict:
    from Backend.helper.scan_manager import dbcheck_manager
    return {"status": "success", "data": dbcheck_manager.get_status()}


async def purge_dead_links_api(payload: dict | None = None) -> dict:
    """Purge dead links.

    - With no body (or {"source": "dbcheck"}): purge the dead entries found by
      the most recent DB check.
    - {"source": "flagged"}: purge every entry flagged is_dead in the DB
      (these come from the background Dead-Link Checker).
    - {"stream_ids": [...]}: purge a specific set.
    """
    from Backend.helper.scan_manager import dbcheck_manager
    payload = payload or {}
    source = str(payload.get("source", "dbcheck")).lower()
    stream_ids = payload.get("stream_ids")

    if stream_ids is not None:
        result = await dbcheck_manager.purge(stream_ids)
    elif source == "flagged":
        try:
            flagged = await db.get_all_dead_links()
            ids = list({d.get("quality_id") for d in flagged if d.get("quality_id")})
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Could not load flagged dead links: {e}")
        result = await dbcheck_manager.purge(ids)
    else:
        result = await dbcheck_manager.purge()

    return {"status": "success" if result.get("ok") else "error", **result}

# ─────────────────────────────────────────────────────────────────────────────
#  Duplicate check & cleanup
# ─────────────────────────────────────────────────────────────────────────────
async def start_duplicate_check_api() -> dict:
    from Backend.helper.scan_manager import duplicate_manager
    result = await duplicate_manager.start()
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("message", "Could not start duplicate scan."))
    return {"status": "success", **result}


async def cancel_duplicate_check_api() -> dict:
    from Backend.helper.scan_manager import duplicate_manager
    result = await duplicate_manager.cancel()
    return {"status": "success" if result.get("ok") else "error", **result}


async def duplicate_check_status_api() -> dict:
    from Backend.helper.scan_manager import duplicate_manager
    return {"status": "success", "data": duplicate_manager.get_status()}


async def purge_duplicates_api(payload: dict | None = None) -> dict:
    from Backend.helper.scan_manager import duplicate_manager
    payload = payload or {}
    stream_ids = payload.get("stream_ids")
    if stream_ids is not None and not isinstance(stream_ids, list):
        raise HTTPException(status_code=400, detail="stream_ids must be a list.")
    result = await duplicate_manager.purge(
        stream_ids=stream_ids,
        delete_all=bool(payload.get("delete_all")),
    )
    if not result.get("ok"):
        raise HTTPException(status_code=409, detail=result.get("message", "Could not start duplicate cleanup."))
    return {"status": "success", **result}


# ─────────────────────────────────────────────────────────────────────────────
#  Bot Admin Manager — use the configured user session to add stream bots as
#  admins in every configured service channel.
# ─────────────────────────────────────────────────────────────────────────────
_bot_admin_apply_state: dict = {
    "running": False,
    "status": "idle",
    "total": 0,
    "done": 0,
    "results": [],
    "error": "",
    "task": None,
}


def _norm_chat_id(ch):
    value = str(ch).strip()
    if not value:
        return None
    return int(value) if value.lstrip("-").isdigit() else value


async def _managed_bots() -> list[dict]:
    bots: list[dict] = []
    for client_id in sorted(multi_clients.keys()):
        client = multi_clients.get(client_id)
        if client is None:
            continue
        me = getattr(client, "me", None)
        if me is None:
            try:
                me = await client.get_me()
            except Exception as exc:
                LOGGER.warning("[BotAdmin] Could not resolve bot client %s: %s", client_id, exc)
                continue
        bots.append({
            "client_id": client_id,
            "user_id": me.id,
            "username": me.username,
            "name": me.first_name or me.username or f"Bot {client_id + 1}",
            "is_main": client_id == 0,
        })
    return bots


def _bot_served_channels() -> list[dict]:
    settings = SettingsManager.current()
    order: list[str] = []
    mapping: dict[str, dict] = {}

    def add(channel, role: str) -> None:
        normalized = _norm_chat_id(channel)
        if normalized is None:
            return
        key = str(normalized)
        if key not in mapping:
            mapping[key] = {"id": normalized, "roles": []}
            order.append(key)
        if role not in mapping[key]["roles"]:
            mapping[key]["roles"].append(role)

    for channel in settings.auth_channels:
        add(channel, "auth")
    # Keep forward compatibility with master settings when those channel roles
    # are enabled later in this customized branch.
    for channel in getattr(settings, "manual_channels", []) or []:
        add(channel, "manual")
    for channel in getattr(settings, "anime_channels", []) or []:
        add(channel, "anime")
    for attr, role in (("announcement_channel", "announce"), ("skip_channel", "skip")):
        channel = getattr(settings, attr, None)
        if channel:
            add(channel, role)
    return [mapping[key] for key in order]


def _bot_admin_privileges() -> ChatPrivileges:
    return ChatPrivileges(
        can_manage_chat=True,
        can_post_messages=True,
        can_edit_messages=True,
        can_delete_messages=True,
        can_invite_users=True,
        can_pin_messages=False,
        can_promote_members=False,
        can_change_info=False,
        can_restrict_members=False,
        can_manage_video_chats=False,
        is_anonymous=False,
    )


def _no_privileges() -> ChatPrivileges:
    return ChatPrivileges(
        can_manage_chat=False,
        can_post_messages=False,
        can_edit_messages=False,
        can_delete_messages=False,
        can_invite_users=False,
        can_pin_messages=False,
        can_promote_members=False,
        can_change_info=False,
        can_restrict_members=False,
        can_manage_video_chats=False,
        is_anonymous=False,
    )


async def _bot_member_status(chat_id, bot_user_id) -> str:
    try:
        member = await Userbot.get_chat_member(chat_id, bot_user_id)
        status = member.status
        if status in (ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR):
            return "admin"
        if status == ChatMemberStatus.BANNED:
            return "banned"
        if status == ChatMemberStatus.RESTRICTED:
            return "restricted"
        if status == ChatMemberStatus.MEMBER:
            return "member"
        return "missing"
    except Exception:
        return "missing"


def _friendly_promote_error(exc) -> str:
    message = str(exc)
    upper = message.upper()
    if "CHAT_ADMIN_REQUIRED" in upper:
        return "The user session is not an admin with the required rights in this channel."
    if "USER_CREATOR" in upper or "ADMIN_RANK" in upper:
        return "The channel creator cannot be modified."
    if "ADD_ADMINS" in upper or ("PROMOTE" in upper and "RIGHT" in upper):
        return "The user session cannot grant these administrator rights."
    if "PARTICIPANT" in upper or "USER_NOT_MUTUAL_CONTACT" in upper:
        return "The bot is not in the channel and could not be added automatically."
    if "BOTS_TOO_MUCH" in upper:
        return "This channel already has the maximum number of bots."
    return message


async def _session_rights(chat_id) -> dict:
    try:
        member = await Userbot.get_chat_member(chat_id, "me")
    except Exception as exc:
        return {"manageable": False, "status": "unknown", "reason": f"Could not check session rights: {exc}"}
    if member.status == ChatMemberStatus.OWNER:
        return {"manageable": True, "status": "owner", "reason": ""}
    if member.status == ChatMemberStatus.ADMINISTRATOR:
        privileges = getattr(member, "privileges", None)
        can_promote = bool(privileges and privileges.can_promote_members)
        return {
            "manageable": can_promote,
            "status": "admin_can_promote" if can_promote else "admin_no_promote",
            "reason": "" if can_promote else "The user session is an admin but does not have Add New Admins permission.",
        }
    return {"manageable": False, "status": "not_admin", "reason": "The user session is not an admin in this channel."}


async def bot_admin_scan_api() -> dict:
    if Userbot is None:
        return {"status": "error", "reason": "no_session", "message": "Configure USER_SESSION_STRING first."}
    bots = await _managed_bots()
    if len(bots) <= 1:
        return {"status": "error", "reason": "single_token", "bots": bots, "message": "Configure at least one extra bot token first."}

    managed_ids = {bot["user_id"] for bot in bots}
    output: list[dict] = []
    for channel in _bot_served_channels():
        chat_id = channel["id"]
        entry = {
            "id": str(chat_id),
            "roles": channel["roles"],
            "name": str(chat_id),
            "accessible": False,
            "manageable": False,
            "session_status": "",
            "reason": "",
            "bots": {},
            "orphans": [],
        }
        try:
            chat = await Userbot.get_chat(chat_id)
            entry["name"] = getattr(chat, "title", None) or getattr(chat, "first_name", None) or str(chat_id)
            entry["accessible"] = True
        except Exception as exc:
            entry["reason"] = f"The user session cannot access this channel: {exc}"
            output.append(entry)
            continue

        rights = await _session_rights(chat_id)
        entry["manageable"] = rights["manageable"]
        entry["session_status"] = rights["status"]
        entry["reason"] = rights["reason"]
        for bot in bots:
            entry["bots"][str(bot["user_id"])] = await _bot_member_status(chat_id, bot["user_id"])

        try:
            async for member in Userbot.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
                user = getattr(member, "user", None)
                if user and getattr(user, "is_bot", False) and user.id not in managed_ids:
                    entry["orphans"].append({
                        "user_id": user.id,
                        "username": user.username,
                        "name": user.first_name or user.username or str(user.id),
                    })
        except Exception as exc:
            LOGGER.warning("[BotAdmin] Could not list admins for %s: %s", chat_id, exc)
        output.append(entry)
    return {"status": "success", "data": {"bots": bots, "channels": output}}


async def _promote_one(chat_id, bot: dict, privileges: ChatPrivileges, retry: bool = True) -> dict:
    label = bot.get("name") or (f"@{bot['username']}" if bot.get("username") else str(bot["user_id"]))
    bot_id = bot["user_id"]
    if await _bot_member_status(chat_id, bot_id) == "admin":
        return {"bot": label, "user_id": bot_id, "status": "already", "message": "Already an admin."}
    try:
        await Userbot.promote_chat_member(chat_id, bot_id, privileges=privileges)
        return {"bot": label, "user_id": bot_id, "status": "added", "message": "Promoted to admin."}
    except FloodWait as exc:
        wait = int(getattr(exc, "value", getattr(exc, "x", 5)) or 5)
        if retry:
            await asyncio.sleep(wait + 1)
            return await _promote_one(chat_id, bot, privileges, retry=False)
        return {"bot": label, "user_id": bot_id, "status": "error", "message": f"Telegram rate limit: wait {wait}s and retry."}
    except Exception as exc:
        upper = str(exc).upper()
        if retry and ("PARTICIPANT" in upper or "USER_NOT_MUTUAL_CONTACT" in upper):
            try:
                await Userbot.add_chat_members(chat_id, bot_id)
                await asyncio.sleep(0.5)
                await Userbot.promote_chat_member(chat_id, bot_id, privileges=privileges)
                return {"bot": label, "user_id": bot_id, "status": "added", "message": "Added and promoted to admin."}
            except Exception as nested:
                return {"bot": label, "user_id": bot_id, "status": "error", "message": _friendly_promote_error(nested)}
        return {"bot": label, "user_id": bot_id, "status": "error", "message": _friendly_promote_error(exc)}


async def _demote_one(chat_id, user) -> dict:
    label = getattr(user, "first_name", None) or (f"@{user.username}" if getattr(user, "username", None) else str(user.id))
    try:
        await Userbot.promote_chat_member(chat_id, user.id, privileges=_no_privileges())
        return {"bot": label, "user_id": user.id, "status": "demoted", "message": "Orphan bot admin rights removed."}
    except Exception as exc:
        return {"bot": label, "user_id": user.id, "status": "error", "message": _friendly_promote_error(exc)}


async def _run_bot_admin_apply(channel_ids, selected, demote_orphans, managed_ids) -> None:
    state = _bot_admin_apply_state
    privileges = _bot_admin_privileges()
    try:
        for raw_channel in channel_ids:
            chat_id = _norm_chat_id(raw_channel)
            channel_result = {"id": str(chat_id), "name": str(chat_id), "items": []}
            try:
                chat = await Userbot.get_chat(chat_id)
                channel_result["name"] = getattr(chat, "title", None) or getattr(chat, "first_name", None) or str(chat_id)
            except Exception as exc:
                channel_result["items"].append({"bot": "—", "status": "error", "message": f"Channel not accessible: {exc}"})
                state["results"].append(channel_result)
                state["done"] += 1
                continue

            rights = await _session_rights(chat_id)
            if not rights["manageable"]:
                channel_result["items"].append({"bot": "—", "status": "skipped", "message": rights["reason"] or "Cannot add admins here."})
                state["results"].append(channel_result)
                state["done"] += 1
                continue

            for bot in selected:
                channel_result["items"].append(await _promote_one(chat_id, bot, privileges))
                await asyncio.sleep(0.3)

            if demote_orphans:
                try:
                    async for member in Userbot.get_chat_members(chat_id, filter=ChatMembersFilter.ADMINISTRATORS):
                        user = getattr(member, "user", None)
                        if user and getattr(user, "is_bot", False) and user.id not in managed_ids:
                            channel_result["items"].append(await _demote_one(chat_id, user))
                            await asyncio.sleep(0.3)
                except Exception as exc:
                    channel_result["items"].append({"bot": "orphans", "status": "error", "message": f"Could not scan orphan bots: {exc}"})

            state["results"].append(channel_result)
            state["done"] += 1
        state["status"] = "completed"
    except Exception as exc:
        LOGGER.error("[BotAdmin] Apply run failed: %s", exc)
        state["status"] = "error"
        state["error"] = str(exc)
    finally:
        state["running"] = False


async def bot_admin_apply_api(payload: dict | None = None) -> dict:
    if Userbot is None:
        raise HTTPException(status_code=503, detail="No USER_SESSION_STRING is configured.")
    if _bot_admin_apply_state["running"]:
        raise HTTPException(status_code=409, detail="A Bot Admin apply run is already active.")
    payload = payload or {}
    channel_ids = payload.get("channel_ids") or []
    if not isinstance(channel_ids, list) or not channel_ids:
        raise HTTPException(status_code=400, detail="Select at least one channel.")
    bots = await _managed_bots()
    if len(bots) <= 1:
        raise HTTPException(status_code=400, detail="Configure a user session and more than one bot token.")
    by_id = {str(bot["user_id"]): bot for bot in bots}
    selected_ids = payload.get("bot_ids")
    selected = [by_id[str(item)] for item in selected_ids if str(item) in by_id] if isinstance(selected_ids, list) and selected_ids else bots
    if not selected:
        raise HTTPException(status_code=400, detail="No matching bots were selected.")
    _bot_admin_apply_state.update({
        "running": True,
        "status": "running",
        "total": len(channel_ids),
        "done": 0,
        "results": [],
        "error": "",
    })
    _bot_admin_apply_state["task"] = asyncio.create_task(
        _run_bot_admin_apply(
            channel_ids,
            selected,
            bool(payload.get("demote_orphans")),
            {bot["user_id"] for bot in bots},
        )
    )
    return {"status": "started", "total": len(channel_ids)}


async def bot_admin_apply_status_api() -> dict:
    state = _bot_admin_apply_state
    return {
        "status": "success",
        "data": {
            "running": state["running"],
            "state": state["status"],
            "total": state["total"],
            "done": state["done"],
            "results": state["results"],
            "error": state["error"],
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Media Edit: subtitles attached to one indexed title
# ─────────────────────────────────────────────────────────────────────────────
async def list_media_subtitles_api(media_type: str, tmdb_id: int, db_index: int) -> dict:
    from Backend.helper.database import convert_objectid_to_str

    media_type = str(media_type or "").strip().lower()
    if media_type not in {"movie", "tv"}:
        raise HTTPException(status_code=400, detail="media_type must be movie or tv.")

    query = {
        "status": "matched",
        "media.media_type": media_type,
        "media.tmdb_id": int(tmdb_id),
        "$or": [
            {"media.db_index": int(db_index)},
            {"media.db_index": {"$exists": False}},
        ],
    }
    rows: list[dict] = []
    for subtitle_db_index in range(1, db.current_db_index + 1):
        storage = db.dbs.get(f"storage_{subtitle_db_index}")
        if storage is None:
            continue
        cursor = storage["subtitles"].find(query).sort([
            ("media.season", 1),
            ("media.episode", 1),
            ("language_code", 1),
            ("updated_at", -1),
        ])
        async for document in cursor:
            item = convert_objectid_to_str(document)
            item["subtitle_db_index"] = subtitle_db_index
            rows.append(item)

    rows.sort(key=lambda item: (
        int((item.get("media") or {}).get("season") or -1),
        int((item.get("media") or {}).get("episode") or -1),
        str(item.get("language_code") or "und"),
        str(item.get("filename") or ""),
    ))
    return {"status": "success", "subtitles": rows, "total": len(rows)}


async def delete_media_subtitle_api(subtitle_id: str, subtitle_db_index: int) -> dict:
    deleted = await db.delete_subtitle(db_index=int(subtitle_db_index), subtitle_id=subtitle_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Subtitle index row was not found.")
    return {
        "status": "success",
        "message": "Subtitle removed from this index. The Telegram source file was not deleted.",
    }
