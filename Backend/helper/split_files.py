"""Filename detection for split Telegram media.

The scanner and live receiver both use this module.  Keep every supported
naming scheme in one place so a file is never indexed by one path and skipped
by the other.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Optional, Tuple

_VIDEO_EXTENSIONS = "mkv|mp4|avi|ts|m4v|mov|wmv|webm|flv|mpeg|mpg"
_VIDEO_EXT_RE = re.compile(rf"(?i)\.({_VIDEO_EXTENSIONS})$")
_NORMALIZE_RE = re.compile(r"[^a-z0-9]+", re.I)


@dataclass(frozen=True)
class SplitFileInfo:
    """A normalized description of one member of a split media set.

    ``kind`` is ``raw`` for a file which can be concatenated directly into a
    video byte stream.  ``zip`` describes split ZIP volumes that reconstruct a
    ZIP archive containing one video entry.
    """

    group_key: str
    part_number: int
    kind: str
    media_filename: str


# Direct byte-split video files.
_RAW_SUFFIX_PATTERNS = (
    # Movie.mkv.001 / Movie.mp4.002
    re.compile(rf"^(?P<base>.+)\.(?P<ext>{_VIDEO_EXTENSIONS})\.(?P<part>\d{{1,5}})$", re.I),
    # Movie.mkv.part001 / Movie.mp4.cd2
    re.compile(
        rf"^(?P<base>.+)\.(?P<ext>{_VIDEO_EXTENSIONS})[.\-_ ]+(?:part|pt|cd|disc|disk)[.\-_ ]*(?P<part>\d{{1,5}})$",
        re.I,
    ),
    # Movie.part001.mkv / Movie.CD 2.mp4 / Movie.Disc-03.mkv.
    # This must precede the generic numeric-before-extension form so `CD 2`
    # and `Disc-03` do not become part of the base title.
    re.compile(
        rf"^(?P<base>.+?)[.\-_ ]+(?:part|pt|cd|disc|disk)[.\-_ ]*(?P<part>\d{{1,5}})\.(?P<ext>{_VIDEO_EXTENSIONS})$",
        re.I,
    ),
    # Movie.001.mkv.  Keep this dot-only: names such as
    # `Series - 001.mkv` and `Series 001.mkv` are normal anime episode
    # releases, not concatenation parts.
    re.compile(rf"^(?P<base>.+?)\.(?P<part>\d{{1,5}})\.(?P<ext>{_VIDEO_EXTENSIONS})$", re.I),
)


# Split ZIP archive volumes.  The archive must contain a video entry.
_ZIP_NUMERIC_RE = re.compile(
    rf"^(?P<base>.+)\.(?P<ext>{_VIDEO_EXTENSIONS})\.zip\.(?P<part>\d{{1,5}})$",
    re.I,
)
# Some release groups split a normal ZIP but leave the original video extension
# out of the volume name, for example:
# `Anaganaga.Oka.Raju.2026.2160p.NF.WEB-DL.MULTI.DDP5.1.H.2.zip.005`.
# The base must still look like media before it is accepted, so ordinary backup
# archives such as `documents.zip.005` are not indexed as movies.
_ZIP_GENERIC_NUMERIC_RE = re.compile(
    r"^(?P<base>.+)\.zip\.(?P<part>\d{1,5})$",
    re.I,
)
_MEDIA_NAME_HINT_RE = re.compile(
    r"""(?ix)
    (?:
        \b(?:2160|1440|1080|720|576|480|360)p\b
        |\bS\d{1,2}E\d{1,3}\b
        |\b(?:web[ ._-]?dl|web[ ._-]?rip|blu[ ._-]?ray|b[dr]rip|hdrip|remux|dvdrip)\b
        |\b(?:x26[45]|h[ ._-]?26[45]|hevc|av1)\b
        |\b(?:ddp?|atmos|aac|dts|truehd)\b
    )
    """
)
# Standard split-ZIP sets use .z01/.z02/... followed by the final .zip file.
_ZIP_ZVOL_RE = re.compile(
    rf"^(?P<base>.+)\.(?P<ext>{_VIDEO_EXTENSIONS})\.z(?P<part>\d{{2,4}})$",
    re.I,
)
_ZIP_FINAL_RE = re.compile(
    rf"^(?P<base>.+)\.(?P<ext>{_VIDEO_EXTENSIONS})\.zip$",
    re.I,
)

# Telegram clients occasionally attach invisible direction / zero-width marks to
# document names.  Those marks must not stop a valid `.mkv.zip.001` match.
_INVISIBLE_FILENAME_CHARS = "\u200b\u200c\u200d\u200e\u200f\u2060\ufeff"
# Some Telegram upload clients report a split ZIP volume as `movie.mkv.001`
# while keeping the MIME type as application/zip.  The receiver uses this only
# as a MIME-aware fallback; a normal `movie.mkv.001` stays a raw byte split.
_ZIP_UPLOAD_FALLBACK_RE = re.compile(
    rf"^(?P<base>.+)\.(?P<ext>{_VIDEO_EXTENSIONS})\.(?P<part>\d{{1,5}})$",
    re.I,
)
_ZIP_MIME_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/x-zip",
    "application/octet-stream",
    "application/x-octet-stream",
}


def _clean_candidate(value: object) -> str:
    """Normalize Telegram filename text without changing ordinary filenames."""
    name = str(value or "")
    for char in _INVISIBLE_FILENAME_CHARS:
        name = name.replace(char, "")
    return name.strip().strip("`\"'")


def _normalize(value: str) -> str:
    """Keep live-upload and rescan split keys identical.

    Scanner cleanup can remove separators such as ``~`` while live messages
    retain them.  Normalizing every non-alphanumeric separator prevents the
    same split file from becoming two different database groups.
    """
    return _NORMALIZE_RE.sub(".", str(value or "").lower()).strip(".")


def _valid_part(value: str) -> Optional[int]:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    # 0 is used by a few splitters, so do not reject it.
    return number if 0 <= number <= 99_999 else None


def _raw_info(match: re.Match[str]) -> Optional[SplitFileInfo]:
    part_number = _valid_part(match.group("part"))
    if part_number is None:
        return None
    base = str(match.group("base") or "").strip()
    ext = str(match.group("ext") or "").strip()
    if base.lower().endswith(f".{ext.lower()}"):
        media_filename = base
    else:
        media_filename = f"{base}.{ext}"
    return SplitFileInfo(
        group_key=f"raw:{_normalize(media_filename)}",
        part_number=part_number,
        kind="raw",
        media_filename=media_filename,
    )


def _zip_info(match: re.Match[str], part_number: int) -> SplitFileInfo:
    media_filename = f"{match.group('base')}.{match.group('ext')}"
    return SplitFileInfo(
        group_key=f"zip:{_normalize(media_filename)}",
        part_number=part_number,
        kind="zip",
        media_filename=media_filename,
    )


def _generic_zip_info(
    match: re.Match[str],
    part_number: int,
    *,
    allow_unmarked: bool = False,
) -> Optional[SplitFileInfo]:
    """Build split ZIP metadata for volume names without a video extension.

    ``name.zip.005`` is accepted by filename alone only when the base contains
    media markers (for example ``2160p`` or ``WEB-DL``).  A Telegram document
    explicitly marked as ZIP/octet-stream can use ``allow_unmarked=True`` so
    rescan and live upload paths behave identically even for short release
    names. The synthetic `.mkv` is only a display/metadata fallback; streaming
    always uses the real video entry discovered inside the reconstructed ZIP.
    """
    base = str(match.group("base") or "").strip().rstrip(".")
    if not base or (not allow_unmarked and not _MEDIA_NAME_HINT_RE.search(base)):
        return None

    media_filename = base if is_video_filename(base) else f"{base}.mkv"
    return SplitFileInfo(
        group_key=f"zip:{_normalize(media_filename)}",
        part_number=part_number,
        kind="zip",
        media_filename=media_filename,
    )


def detect_split_file(filename: str) -> Optional[SplitFileInfo]:
    """Return split metadata for a supported filename, otherwise ``None``.

    Supported direct-video forms include ``.mkv.001``, ``.001.mkv``,
    ``.part001.mkv``, ``.mkv.part001``, ``.CD1.mkv`` and ``.Disc-02.mkv``.
    Supported archive forms include ``.mkv.zip.001``, media-labelled
    ``Release.2026.2160p.WEB-DL.zip.001``, and standard ``.z01`` + final
    ``.zip`` volume sets.
    """
    if not filename:
        return None

    name = _clean_candidate(filename)
    for pattern in _RAW_SUFFIX_PATTERNS:
        match = pattern.match(name)
        if match:
            return _raw_info(match)

    match = _ZIP_NUMERIC_RE.match(name)
    if match:
        part_number = _valid_part(match.group("part"))
        if part_number is not None:
            return _zip_info(match, part_number)

    match = _ZIP_GENERIC_NUMERIC_RE.match(name)
    if match:
        part_number = _valid_part(match.group("part"))
        if part_number is not None:
            return _generic_zip_info(match, part_number)

    match = _ZIP_ZVOL_RE.match(name)
    if match:
        part_number = _valid_part(match.group("part"))
        if part_number is not None:
            return _zip_info(match, part_number)

    match = _ZIP_FINAL_RE.match(name)
    if match:
        # The final .zip volume must follow every .zNN part.  A large sentinel
        # keeps it last while avoiding a second lookup after every insertion.
        return _zip_info(match, 1_000_000)

    return None


def parse_split_info(filename: str) -> Optional[Tuple[str, int]]:
    """Backward-compatible `(group_key, part_number)` helper."""
    info = detect_split_file(filename)
    return (info.group_key, info.part_number) if info else None


def strip_part_suffix(filename: str) -> str:
    """Return the clean original media filename for a split member."""
    info = detect_split_file(filename)
    return info.media_filename if info else filename


def is_video_filename(filename: str) -> bool:
    """True for a direct video file, independent of Telegram MIME type."""
    return bool(filename and _VIDEO_EXT_RE.search(filename.strip()))


def find_split_source(*candidates: object) -> tuple[str | None, SplitFileInfo | None]:
    """Return a split filename from a Telegram document name or caption.

    File names are checked first.  Captions are also checked line by line so a
    filename wrapped in Markdown/backticks or followed by a short note is still
    accepted by the live receiver.
    """
    for candidate in candidates:
        raw = _clean_candidate(candidate)
        if not raw:
            continue
        direct = detect_split_file(raw)
        if direct:
            return raw, direct
        # A caption can contain a filename on one line plus an unrelated note.
        for line in raw.splitlines():
            line = _clean_candidate(line)
            if not line:
                continue
            info = detect_split_file(line)
            if info:
                return line, info
            # Common formatted captions: `filename` — upload note
            for token in (line.split(" — ")[0], line.split(" - ")[0]):
                token = _clean_candidate(token)
                info = detect_split_file(token)
                if info:
                    return token, info
    return None, None


def detect_split_upload(filename: object, mime_type: object = "") -> Optional[SplitFileInfo]:
    """Resolve a split member received as a Telegram document.

    The exact normal forms are handled by :func:`detect_split_file`.  The
    MIME-aware fallback supports clients that hide the `.zip` middle suffix but
    still mark the document as ZIP/octet-stream.
    """
    name = _clean_candidate(filename)
    info = detect_split_file(name)
    if info:
        return info
    mime = str(mime_type or "").lower().split(";", 1)[0].strip()
    if mime not in _ZIP_MIME_TYPES:
        return None
    # ZIP documents sometimes use simple volume names such as
    # `Movie.Release.zip.001` with no `.mkv` before `.zip`.  The MIME type is
    # authoritative here, so allow even short names after confirming the
    # numeric ZIP-volume shape. This is intentionally after normal filename
    # matching to avoid indexing unrelated archives by name alone.
    match = _ZIP_GENERIC_NUMERIC_RE.match(name)
    if match:
        part_number = _valid_part(match.group("part"))
        if part_number is not None:
            info = _generic_zip_info(match, part_number, allow_unmarked=True)
            if info:
                return info

    match = _ZIP_UPLOAD_FALLBACK_RE.match(name)
    if not match:
        return None
    part_number = _valid_part(match.group("part"))
    if part_number is None:
        return None
    media_filename = f"{match.group('base')}.{match.group('ext')}"
    return SplitFileInfo(
        group_key=f"zip:{_normalize(media_filename)}",
        part_number=part_number,
        kind="zip",
        media_filename=media_filename,
    )

def split_metadata_fields(channel: int, quality: object, info: SplitFileInfo) -> dict:
    """Return the canonical database metadata for one split part."""
    return {
        "group_key": f"{int(channel)}:{str(quality or 'HD')}:{info.group_key}",
        "part_number": info.part_number,
        "split_kind": info.kind,
        "media_filename": info.media_filename,
    }
