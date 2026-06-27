from asyncio import create_task, sleep as asleep, Queue, Lock
import Backend
from Backend.helper.task_manager import edit_message
from Backend.logger import LOGGER
from Backend import db
from Backend.helper.settings_manager import SettingsManager
from Backend.helper.pyro import clean_filename, get_readable_file_size, remove_urls
from Backend.helper.metadata import metadata
from pyrogram import filters, Client
from pyrogram.types import Message
from pyrogram.errors import FloodWait
from pyrogram.enums.parse_mode import ParseMode
from Backend.helper.metadata import extract_default_id
from Backend.helper.split_files import (
    detect_split_upload,
    strip_part_suffix,
    find_split_source,
    find_legacy_bare_split_source,
    resolve_legacy_bare_split_candidates,
    split_metadata_fields,
)
from Backend.helper.subtitle_service import index_subtitle, relink_unmatched_subtitles
from Backend.helper.subtitle_constants import is_subtitle_file



file_queue = Queue()
db_lock = Lock()


def _split_source_info(message: Message):
    """Return the canonical source name + split info for a channel upload."""
    file = message.video or message.document
    filename = getattr(file, "file_name", "") or ""
    source, info = find_split_source(
        filename,
        message.caption or "",
        clean_filename(filename),
        clean_filename(message.caption or ""),
    )
    if info:
        return source, info
    # MIME-aware fallback for Telegram clients which expose a ZIP part as
    # `movie.mkv.001` or append invisible characters to its document name.
    info = detect_split_upload(filename, getattr(file, "mime_type", "") or "")
    if info:
        return filename, info
    return None, None


def _split_source_name(message: Message) -> str | None:
    source, _ = _split_source_info(message)
    return source


# A normal live upload is handled one message at a time.  Legacy raw volumes
# named `Movie.001.mkv` cannot be trusted from the filename alone, so look only
# at recently posted sibling media before promoting the current upload.  The
# scanner uses the same validation rule across its batches.
_LEGACY_SPLIT_LIVE_LOOKBACK = 200


def _legacy_bare_split_candidate(message: Message):
    file = message.video or message.document
    if file is None:
        return None
    message_id = int(getattr(message, "id", 0) or 0)
    if message_id <= 0:
        return None
    filename = getattr(file, "file_name", "") or ""
    caption = message.caption or ""
    source, info = find_legacy_bare_split_source(
        filename,
        caption,
        clean_filename(filename),
        clean_filename(caption),
    )
    return (message_id, source, info) if source and info else None


async def _contextual_legacy_split_for_live_upload(client: Client, message: Message):
    """Return split metadata for the current legacy `.001.mkv` upload.

    A new `.001` remains normal until a matching `.002` exists.  When `.002`
    arrives, the preceding `.001` is found from the channel history and the
    database converts that indexed normal row into a virtual-stream part.
    This never accepts `.720.mkv`, `.1.mkv`, or any non-zero-padded suffix.
    """
    current = _legacy_bare_split_candidate(message)
    if not current:
        return None, None

    message_id, source, _info = current
    start = max(1, message_id - _LEGACY_SPLIT_LIVE_LOOKBACK)
    candidates = []
    try:
        history = await client.get_messages(message.chat.id, list(range(start, message_id + 1)))
        if not isinstance(history, list):
            history = [history]
        for sibling in history:
            if sibling is None or getattr(sibling, "empty", False):
                continue
            candidate = _legacy_bare_split_candidate(sibling)
            if candidate:
                candidates.append((candidate[0], candidate[2]))
    except FloodWait as exc:
        LOGGER.info("[LegacySplit] Live context postponed by FloodWait %ss.", exc.value)
        return None, None
    except Exception as exc:
        LOGGER.debug("[LegacySplit] Live context unavailable for msg %s: %s", message_id, exc)
        return None, None

    accepted = resolve_legacy_bare_split_candidates(candidates)
    info = accepted.get(message_id)
    if not info:
        return None, None
    LOGGER.info(
        "[LegacySplit] Live upload msg %s accepted after consecutive sibling validation.",
        message_id,
    )
    return source, info


def _is_supported_media(message: Message) -> bool:
    if message.video:
        return True
    if message.document:
        mime_type = (message.document.mime_type or "").lower()
        if mime_type.startswith("video/"):
            return True
        # `.mkv.zip.001` volumes normally arrive as application/zip or octet-stream.
        return _split_source_info(message)[1] is not None
    return False


def _is_subtitle_message(message: Message) -> bool:
    if not message.document or message.video:
        return False
    return is_subtitle_file(
        message.document.file_name or message.caption or "",
        message.document.mime_type or "",
    )


async def _index_subtitle_message(message: Message) -> None:
    document = message.document
    channel = int(str(message.chat.id).replace("-100", ""))
    record = await index_subtitle(
        db,
        channel=channel,
        msg_id=message.id,
        filename=document.file_name or message.caption or "subtitle.srt",
        caption=message.caption or "",
        raw_size=document.file_size or 0,
        size=get_readable_file_size(document.file_size or 0),
        mime_type=document.mime_type or "",
    )
    LOGGER.info(
        "Subtitle indexed: %s [%s] → %s",
        record.get("filename"),
        record.get("language_code"),
        record.get("status"),
    )

async def process_file():
    while True:
        metadata_info, channel, msg_id, size, raw_size, title = await file_queue.get()
        async with db_lock:
            updated_id = await db.insert_media(metadata_info, channel=channel, msg_id=msg_id, size=size, raw_size=raw_size, name=title)
            if updated_id:
                LOGGER.info(f"{metadata_info['media_type']} updated with ID: {updated_id}")
                await relink_unmatched_subtitles(db, limit=150)
            else:
                LOGGER.info("Update failed due to validation errors.")
        file_queue.task_done()

for _ in range(1):
    create_task(process_file())


@Client.on_message(filters.channel & (filters.document | filters.video))
async def file_receive_handler(client: Client, message: Message):
    if str(message.chat.id) in SettingsManager.current().auth_channels:
        try:
            if _is_subtitle_message(message):
                await _index_subtitle_message(message)
                return
            if _is_supported_media(message):
                file = message.video or message.document
                title = message.caption or file.file_name
                split_source, split_upload_info = _split_source_info(message)
                legacy_candidate = _legacy_bare_split_candidate(message)
                if not split_upload_info:
                    split_source, split_upload_info = await _contextual_legacy_split_for_live_upload(client, message)
                metadata_source = split_source or title
                msg_id = message.id
                raw_size = file.file_size or 0
                size = get_readable_file_size(raw_size)
                channel = str(message.chat.id).replace("-100", "")

                metadata_input = metadata_source if split_upload_info else clean_filename(metadata_source)
                metadata_info = await metadata(metadata_input, int(channel), msg_id)
                if metadata_info is None:
                    LOGGER.warning(f"Metadata failed for file: {title} (ID: {msg_id})")
                    return
                if legacy_candidate and not split_upload_info:
                    metadata_info["legacy_source_filename"] = legacy_candidate[1]

                title = remove_urls(metadata_source if metadata_info.get('group_key') else title)
                if not metadata_info.get('group_key'):
                    recovered_split = split_upload_info or find_split_source(title, metadata_source)[1]
                    if recovered_split:
                        metadata_info.update(split_metadata_fields(int(channel), metadata_info.get('quality'), recovered_split))
                        LOGGER.info("[SplitRecovery] live msg %s: %s → part %s", msg_id, title, recovered_split.part_number)
                if metadata_info.get('group_key'):
                    title = metadata_info.get('media_filename') or strip_part_suffix(title)
                if not title.lower().endswith(('.mkv', '.mp4', '.avi', '.ts', '.m4v', '.mov', '.wmv', '.webm', '.flv', '.mpeg', '.mpg')):
                    title += '.mkv'

                if Backend.USE_DEFAULT_ID:
                    new_caption = (message.caption + "\n\n" + Backend.USE_DEFAULT_ID) if message.caption else Backend.USE_DEFAULT_ID
                    create_task(edit_message(
                        chat_id=message.chat.id,
                        msg_id=message.id,
                        new_caption=new_caption
                    ))

                await file_queue.put((metadata_info, int(channel), msg_id, size, raw_size, title))
            else:
                file = message.video or message.document
                LOGGER.info(
                    "Ignoring unsupported channel upload: name=%r mime=%r message=%s",
                    getattr(file, "file_name", "") if file else "",
                    getattr(file, "mime_type", "") if file else "",
                    message.id,
                )
        except FloodWait as e:
            LOGGER.info(f"Sleeping for {str(e.value)}s")
            await asleep(e.value)
            await message.reply_text(
                text=f"Got Floodwait of {str(e.value)}s",
                disable_web_page_preview=True,
                parse_mode=ParseMode.MARKDOWN
            )
    else:
        await message.reply_text("> Channel is not in AUTH_CHANNEL")
        

@Client.on_edited_message(filters.channel & (filters.document | filters.video))
async def file_edited_handler(client: Client, message: Message):
    if str(message.chat.id) in SettingsManager.current().auth_channels:
        try:
            if _is_subtitle_message(message):
                await _index_subtitle_message(message)
                return
            if _is_supported_media(message):
                file = message.video or message.document
                title = message.caption or file.file_name
                split_source, split_upload_info = _split_source_info(message)
                legacy_candidate = _legacy_bare_split_candidate(message)
                if not split_upload_info:
                    split_source, split_upload_info = await _contextual_legacy_split_for_live_upload(client, message)
                metadata_source = split_source or title
                msg_id = message.id
                raw_size = file.file_size or 0
                size = get_readable_file_size(raw_size)
                channel = str(message.chat.id).replace("-100", "")

                override_id = extract_default_id(message.caption) if message.caption else None

                if override_id:
                    LOGGER.info(f"Detected override ID '{override_id}' in edited message {msg_id}")
                    
                    await db.remove_media_part(int(channel), msg_id)

                    metadata_input = metadata_source if split_upload_info else clean_filename(metadata_source)
                    metadata_info = await metadata(metadata_input, int(channel), msg_id, override_id=override_id)
                    if metadata_info is None:
                        LOGGER.warning(f"Metadata failed for edited file: {title} (ID: {msg_id})")
                        return
                    if legacy_candidate and not split_upload_info:
                        metadata_info["legacy_source_filename"] = legacy_candidate[1]

                    title = remove_urls(metadata_source if metadata_info.get('group_key') else title)
                    if not metadata_info.get('group_key'):
                        recovered_split = split_upload_info or find_split_source(title, metadata_source)[1]
                        if recovered_split:
                            metadata_info.update(split_metadata_fields(int(channel), metadata_info.get('quality'), recovered_split))
                            LOGGER.info("[SplitRecovery] edited msg %s: %s → part %s", msg_id, title, recovered_split.part_number)
                    if metadata_info.get('group_key'):
                        title = metadata_info.get('media_filename') or strip_part_suffix(title)
                    if not title.lower().endswith(('.mkv', '.mp4', '.avi', '.ts', '.m4v', '.mov', '.wmv', '.webm', '.flv', '.mpeg', '.mpg')):
                        title += '.mkv'

                    await file_queue.put((metadata_info, int(channel), msg_id, size, raw_size, title))
            else:
                pass
        except Exception as e:
            LOGGER.error(f"Error handling edited generic file {message.id}: {e}")

@Client.on_deleted_messages(filters.channel)
async def file_deleted_handler(client: Client, messages: list[Message]):
    try:
        
        for message in messages:
            if message.chat and str(message.chat.id) in SettingsManager.current().auth_channels:
                channel = str(message.chat.id).replace("-100", "")
                msg_id = message.id
                
                try:
                    deleted = await db.remove_media_part(int(channel), msg_id)
                    subtitle_deleted = await db.delete_subtitle_by_message(int(channel), msg_id)
                    
                    if deleted or subtitle_deleted:
                        LOGGER.info(f"Automatically purged deleted message {msg_id} from database.")
                except Exception as ex:
                    LOGGER.error(f"Failed to scrub deleted message {msg_id}: {ex}")
                    
    except Exception as e:
        LOGGER.error(f"Error handling deleted messages: {e}")
