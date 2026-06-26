"""Remote ZIP entry reader for numbered split ZIP uploads.

The input parts are Telegram files that reconstruct one ordinary ZIP archive
when placed in numeric order.  Video files are normally incompressible, but
both stored and deflated ZIP entries are handled.  Deflated entries are read
sequentially when a player seeks because ZIP itself has no random-access index
for decompressed bytes.
"""
from __future__ import annotations

from dataclasses import dataclass
import struct
import time
import zlib
from typing import Dict, List, Optional

from Backend.helper.virtual_dl import virtual_stream_generator
from Backend.logger import LOGGER

_VIDEO_SUFFIXES = (".mkv", ".mp4", ".avi", ".ts", ".m4v", ".mov", ".wmv", ".webm", ".flv", ".mpeg", ".mpg")
_EOCD_SIGNATURE = b"PK\x05\x06"
_ZIP64_EOCD_SIGNATURE = b"PK\x06\x06"
_ZIP64_LOCATOR_SIGNATURE = b"PK\x06\x07"
_CENTRAL_SIGNATURE = b"PK\x01\x02"
_LOCAL_SIGNATURE = b"PK\x03\x04"
_MAX_EOCD_SEARCH = 65_557  # 64 KiB ZIP comment + EOCD header


class SplitArchiveError(RuntimeError):
    """The uploaded pieces do not reconstruct a supported playable archive."""


@dataclass(frozen=True)
class ArchiveVideoEntry:
    filename: str
    compression: int
    flags: int
    compressed_size: int
    uncompressed_size: int
    data_offset: int

    @property
    def compression_name(self) -> str:
        return {0: "stored", 8: "deflate"}.get(self.compression, f"method-{self.compression}")


async def _read_virtual_bytes(
    parts: List[Dict],
    start: int,
    length: int,
    streamer,
    client_index: int,
    stream_id: str,
) -> bytes:
    if length <= 0:
        return b""
    end = start + length - 1
    chunks = bytearray()
    async for chunk in virtual_stream_generator(
        parts=parts,
        start=start,
        end=end,
        chunk_size=64 * 1024,
        streamer=streamer,
        client_index=client_index,
        request=None,
        meta={"kind": "split_zip_probe"},
        stream_id=stream_id,
        parallelism=1,
        prefetch_count=1,
    ):
        chunks.extend(chunk)
        if len(chunks) >= length:
            break
    if len(chunks) < length:
        raise SplitArchiveError("ZIP volume is incomplete or unavailable")
    return bytes(chunks[:length])


def _zip64_values(extra: bytes, *, uncompressed: int, compressed: int, local_offset: int, disk_start: int) -> tuple[int, int, int, int]:
    offset = 0
    while offset + 4 <= len(extra):
        field_id, field_len = struct.unpack_from("<HH", extra, offset)
        offset += 4
        field = extra[offset:offset + field_len]
        offset += field_len
        if field_id != 0x0001:
            continue
        cursor = 0

        def take_qword(current: int) -> tuple[int, int]:
            if cursor_ref[0] + 8 > len(field):
                raise SplitArchiveError("Invalid ZIP64 extra field")
            value = struct.unpack_from("<Q", field, cursor_ref[0])[0]
            cursor_ref[0] += 8
            return value, cursor_ref[0]

        cursor_ref = [cursor]
        if uncompressed == 0xFFFFFFFF:
            uncompressed, _ = take_qword(cursor)
        if compressed == 0xFFFFFFFF:
            compressed, _ = take_qword(cursor)
        if local_offset == 0xFFFFFFFF:
            local_offset, _ = take_qword(cursor)
        if disk_start == 0xFFFF:
            if cursor_ref[0] + 4 > len(field):
                raise SplitArchiveError("Invalid ZIP64 disk number")
            disk_start = struct.unpack_from("<I", field, cursor_ref[0])[0]
        return uncompressed, compressed, local_offset, disk_start
    return uncompressed, compressed, local_offset, disk_start


async def _central_directory_location(parts: List[Dict], archive_size: int, streamer, client_index: int, stream_id: str) -> tuple[int, int, int]:
    tail_len = min(archive_size, _MAX_EOCD_SEARCH)
    tail_start = archive_size - tail_len
    tail = await _read_virtual_bytes(parts, tail_start, tail_len, streamer, client_index, f"{stream_id}-eocd")
    eocd_at = tail.rfind(_EOCD_SIGNATURE)
    if eocd_at < 0 or eocd_at + 22 > len(tail):
        raise SplitArchiveError("Could not find ZIP end record; upload every .zip.001 part")

    eocd = struct.unpack_from("<4s4H2LH", tail, eocd_at)
    _sig, disk_number, cd_disk, _entries_this_disk, total_entries, cd_size, cd_offset, _comment_len = eocd
    if disk_number != 0 or cd_disk != 0:
        raise SplitArchiveError("Multi-disk .z01 ZIP files are not supported; use .zip.001 parts")

    if total_entries != 0xFFFF and cd_size != 0xFFFFFFFF and cd_offset != 0xFFFFFFFF:
        return int(cd_offset), int(cd_size), int(total_entries)

    locator_offset = tail_start + eocd_at - 20
    if locator_offset < 0:
        raise SplitArchiveError("ZIP64 locator is missing")
    locator = await _read_virtual_bytes(parts, locator_offset, 20, streamer, client_index, f"{stream_id}-zip64loc")
    sig, _start_disk, zip64_offset, total_disks = struct.unpack("<4sIQI", locator)
    if sig != _ZIP64_LOCATOR_SIGNATURE or total_disks != 1:
        raise SplitArchiveError("Unsupported ZIP64 multi-disk archive")

    record = await _read_virtual_bytes(parts, int(zip64_offset), 56, streamer, client_index, f"{stream_id}-zip64")
    values = struct.unpack("<4sQHHIIQQQQ", record)
    if values[0] != _ZIP64_EOCD_SIGNATURE:
        raise SplitArchiveError("Invalid ZIP64 end record")
    _sig, _record_size, _made, _needed, disk_number, cd_disk, _entries_disk, entries, cd_size, cd_offset = values
    if disk_number != 0 or cd_disk != 0:
        raise SplitArchiveError("Unsupported ZIP64 multi-disk archive")
    return int(cd_offset), int(cd_size), int(entries)


async def inspect_split_zip(
    parts: List[Dict],
    archive_size: int,
    streamer,
    client_index: int,
    stream_id: str,
) -> ArchiveVideoEntry:
    """Find the largest video entry inside a reassembled, split ZIP archive."""
    cd_offset, cd_size, _entry_count = await _central_directory_location(
        parts, archive_size, streamer, client_index, stream_id
    )
    if cd_size <= 0 or cd_offset < 0 or cd_offset + cd_size > archive_size:
        raise SplitArchiveError("Invalid ZIP central directory")

    directory = await _read_virtual_bytes(parts, cd_offset, cd_size, streamer, client_index, f"{stream_id}-cd")
    cursor = 0
    candidates: list[tuple[str, int, int, int, int]] = []
    while cursor + 46 <= len(directory):
        if directory[cursor:cursor + 4] != _CENTRAL_SIGNATURE:
            break
        fields = struct.unpack_from("<4s6H3L5H2L", directory, cursor)
        flags = int(fields[3])
        compression = int(fields[4])
        compressed_size = int(fields[8])
        uncompressed_size = int(fields[9])
        filename_len = int(fields[10])
        extra_len = int(fields[11])
        comment_len = int(fields[12])
        disk_start = int(fields[13])
        local_offset = int(fields[16])
        total_len = 46 + filename_len + extra_len + comment_len
        if cursor + total_len > len(directory):
            raise SplitArchiveError("Truncated ZIP central-directory entry")

        name_raw = directory[cursor + 46: cursor + 46 + filename_len]
        extra = directory[cursor + 46 + filename_len: cursor + 46 + filename_len + extra_len]
        encoding = "utf-8" if flags & 0x800 else "cp437"
        filename = name_raw.decode(encoding, errors="replace")
        uncompressed_size, compressed_size, local_offset, disk_start = _zip64_values(
            extra,
            uncompressed=uncompressed_size,
            compressed=compressed_size,
            local_offset=local_offset,
            disk_start=disk_start,
        )
        if disk_start == 0 and filename.lower().endswith(_VIDEO_SUFFIXES) and not filename.endswith("/"):
            candidates.append((filename, flags, compression, compressed_size, uncompressed_size, local_offset))
        cursor += total_len

    if not candidates:
        raise SplitArchiveError("No MKV/MP4/video file found inside the ZIP archive")

    filename, flags, compression, compressed_size, uncompressed_size, local_offset = max(candidates, key=lambda item: item[4])
    if flags & 0x1:
        raise SplitArchiveError("Encrypted ZIP archives are not supported")
    if compression not in (0, 8):
        raise SplitArchiveError(f"ZIP compression method {compression} is not supported")

    local_header = await _read_virtual_bytes(parts, local_offset, 30, streamer, client_index, f"{stream_id}-local")
    local_fields = struct.unpack("<4s5H3L2H", local_header)
    if local_fields[0] != _LOCAL_SIGNATURE:
        raise SplitArchiveError("Invalid ZIP local file header")
    local_flags = int(local_fields[2])
    local_method = int(local_fields[3])
    local_filename_len = int(local_fields[9])
    local_extra_len = int(local_fields[10])
    if local_flags & 0x1:
        raise SplitArchiveError("Encrypted ZIP archives are not supported")
    if local_method != compression:
        raise SplitArchiveError("ZIP compression metadata mismatch")

    entry = ArchiveVideoEntry(
        filename=filename,
        compression=compression,
        flags=flags,
        compressed_size=compressed_size,
        uncompressed_size=uncompressed_size,
        data_offset=int(local_offset) + 30 + local_filename_len + local_extra_len,
    )
    LOGGER.info(
        "[SplitZip] resolved %s (%s, %s bytes) from %s archive parts",
        entry.filename,
        entry.compression_name,
        entry.uncompressed_size,
        len(parts),
    )
    return entry


async def zip_entry_stream_generator(
    *,
    parts: List[Dict],
    entry: ArchiveVideoEntry,
    start: int,
    end: int,
    streamer,
    client_index: int,
    request,
    meta: Optional[dict],
    stream_id: str,
    parallelism: int,
    prefetch_count: int,
):
    """Yield decompressed video bytes for a Stremio byte range."""
    if start < 0 or end < start or end >= entry.uncompressed_size:
        raise SplitArchiveError("Invalid ZIP media range")

    if entry.compression == 0:
        async for chunk in virtual_stream_generator(
            parts=parts,
            start=entry.data_offset + start,
            end=entry.data_offset + end,
            chunk_size=1024 * 1024,
            streamer=streamer,
            client_index=client_index,
            request=request,
            meta=meta,
            stream_id=stream_id,
            parallelism=parallelism,
            prefetch_count=prefetch_count,
        ):
            yield chunk
        return

    # Deflated data cannot be jumped to directly.  Start at the entry boundary,
    # discard decompressed bytes before `start`, then return only the requested
    # interval.  Normal playback begins at offset zero; long random seeks will
    # take proportionally longer but remain correct without writing a huge temp
    # movie file on Hugging Face storage.
    decompressor = zlib.decompressobj(-zlib.MAX_WBITS)
    remaining = end - start + 1
    skip = start
    compressed_end = entry.data_offset + entry.compressed_size - 1
    async for compressed in virtual_stream_generator(
        parts=parts,
        start=entry.data_offset,
        end=compressed_end,
        chunk_size=1024 * 1024,
        streamer=streamer,
        client_index=client_index,
        request=request,
        meta=meta,
        stream_id=stream_id,
        parallelism=parallelism,
        prefetch_count=prefetch_count,
    ):
        output = decompressor.decompress(compressed)
        if not output:
            continue
        if skip:
            if len(output) <= skip:
                skip -= len(output)
                continue
            output = output[skip:]
            skip = 0
        if len(output) >= remaining:
            yield output[:remaining]
            return
        yield output
        remaining -= len(output)

    tail = decompressor.flush()
    if tail and remaining:
        if skip:
            tail = tail[skip:]
            skip = 0
        if tail:
            yield tail[:remaining]
