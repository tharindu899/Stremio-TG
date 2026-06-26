import asyncio

from Backend import db
from Backend.logger import LOGGER
from Backend.helper.custom_dl import ACTIVE_STREAMS, RECENT_STREAMS

async def track_usage(stream_id: str, token: str, token_data: dict):
    await asyncio.sleep(2)
    limits = token_data.get("limits", {}) if token_data else {}
    usage = token_data.get("usage", {}) if token_data else {}
    daily_limit_gb = limits.get("daily_limit_gb")
    monthly_limit_gb = limits.get("monthly_limit_gb")
    initial_daily_bytes = usage.get("daily", {}).get("bytes", 0)
    initial_monthly_bytes = usage.get("monthly", {}).get("bytes", 0)
    last_tracked_bytes = 0
    update_interval = 10
    try:
        while True:
            await asyncio.sleep(update_interval)
            stream_info = ACTIVE_STREAMS.get(stream_id)
            if not stream_info:
                for rec in RECENT_STREAMS:
                    if rec.get("stream_id") == stream_id:
                        final_bytes = rec.get("total_bytes", 0)
                        delta = final_bytes - last_tracked_bytes
                        if delta > 0:
                            try:
                                await db.update_token_usage(token, delta)
                            except Exception as e:
                                LOGGER.error(f"Final usage update failed: {e}")
                        break
                return
            current_bytes = stream_info.get("total_bytes", 0)
            delta = current_bytes - last_tracked_bytes
            if delta > 0:
                try:
                    await db.update_token_usage(token, delta)
                    last_tracked_bytes = current_bytes
                except Exception as e:
                    LOGGER.error(f"Periodic usage update failed: {e}")
            if daily_limit_gb and daily_limit_gb > 0:
                current_daily_gb = (initial_daily_bytes + current_bytes) / (1024 ** 3)
                if current_daily_gb >= daily_limit_gb:
                    LOGGER.debug(f"Daily limit reached for token, stream {stream_id} may be blocked by verify_token")
            if monthly_limit_gb and monthly_limit_gb > 0:
                current_monthly_gb = (initial_monthly_bytes + current_bytes) / (1024 ** 3)
                if current_monthly_gb >= monthly_limit_gb:
                    LOGGER.debug(f"Monthly limit reached for token, stream {stream_id} may be blocked by verify_token")
    except asyncio.CancelledError:
        stream_info = ACTIVE_STREAMS.get(stream_id)
        if stream_info:
            current_bytes = stream_info.get("total_bytes", 0)
            delta = current_bytes - last_tracked_bytes
            if delta > 0:
                try:
                    await db.update_token_usage(token, delta)
                    LOGGER.info(f"Cancelled - final update for {stream_id}: {delta} bytes")
                except Exception as e:
                    LOGGER.error(f"Cancelled usage update failed: {e}")
