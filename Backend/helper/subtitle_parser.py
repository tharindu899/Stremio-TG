"""Pure parsing helpers for subtitle filenames and Telegram captions."""
from __future__ import annotations

import re
import unicodedata
from pathlib import PurePath
from typing import Optional

from Backend.helper.subtitle_constants import (
    LANGUAGE_ALIASES,
    LANGUAGE_NAMES,
    extension_from_filename,
    language_name,
)
from Backend.helper.subtitle_models import SubtitleIdentity

_EXPLICIT_SUB_TAG = re.compile(
    r"\[\s*sub\s*:\s*(?P<id>tt\d{5,12}|tmdb\s*[:=]?\s*\d+)"
    r"(?P<tail>[^\]]*)\]",
    re.IGNORECASE,
)
_IMDB_ID = re.compile(r"\b(tt\d{5,12})\b", re.IGNORECASE)
_TMDB_ID = re.compile(r"\btmdb\s*[:=]\s*(\d+)\b", re.IGNORECASE)
_SEASON_EPISODE = re.compile(
    r"\b(?:s(?P<s1>\d{1,2})[ ._\-]*e(?P<e1>\d{1,3})|"
    r"(?P<s2>\d{1,2})x(?P<e2>\d{1,3})|"
    r"season[ ._\-]*(?P<s3>\d{1,2})[ ._\-]*episode[ ._\-]*(?P<e3>\d{1,3}))\b",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b((?:19|20)\d{2})\b")
_URL = re.compile(r"\b(?:https?|ftp)://\S+", re.IGNORECASE)
_TECHNICAL_MARKER = re.compile(
    r"\b(?:2160p|1080p|720p|576p|480p|360p|4k|uhd|fhd|hdrip|webrip|web[ ._-]?dl|"
    r"bluray|bdrip|dvdrip|remux|x26[45]|hevc|avc|h\.?(?:264|265)|aac|ddp?\+?|"
    r"atmos|proper|repack|extended|uncut|complete|hq|hq[ ._-]?hdrip|esub|subtitle|subtitles|subs?|"
    r"dubbed|dual|audio|stereo|mono|(?:2|5|7)[ .]?1|\d{1,2}ch|(?:8|10|12)bit|hi10p|"
    r"multi(?:sub)?|yts|rarbg)\b",
    re.IGNORECASE,
)


def normalize_title(value: str) -> str:
    """Normalize titles for stable matching while retaining Unicode letters."""
    value = unicodedata.normalize("NFKC", value or "").lower()
    value = re.sub(r"\b(?:the|a|an)\b\s+", "", value)
    value = re.sub(r"[^\w\s]", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


def _word_pattern(alias: str) -> re.Pattern:
    if re.fullmatch(r"[a-z]{2,3}", alias, re.IGNORECASE):
        return re.compile(rf"(?<![a-z0-9]){re.escape(alias)}(?![a-z0-9])", re.IGNORECASE)
    return re.compile(re.escape(alias), re.IGNORECASE)


def normalize_language(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    if candidate in LANGUAGE_NAMES:
        return candidate
    for code, aliases in LANGUAGE_ALIASES.items():
        for alias in aliases:
            if candidate == alias.lower():
                return code
    return "und"


def detect_language(*values: str) -> str:
    """Detect the subtitle language, preferring labels nearest ``sub``/``subtitle``.

    Filenames often include both a movie language and a subtitle language, for
    example ``Malayalam ... sinhala sub.srt``. Returning the first language
    would incorrectly choose Malayalam, so each matching label is scored by
    its proximity to subtitle markers and its position in the filename.
    """
    joined = " ".join(v for v in values if v)
    marker = re.compile(r"\b(?:sub(?:title)?s?|srt|ass|ssa|vtt|cc|caption|esub)\b", re.IGNORECASE)
    markers = [match.span() for match in marker.finditer(joined)]
    candidates: list[tuple[float, str]] = []

    for code, aliases in LANGUAGE_ALIASES.items():
        for alias in aliases:
            for match in _word_pattern(alias).finditer(joined):
                start, end = match.span()
                distance = min(
                    (min(abs(start - marker_end), abs(marker_start - end)) for marker_start, marker_end in markers),
                    default=10_000,
                )
                # A language label directly beside a subtitle marker is a
                # strong signal; later labels break ties in common filenames.
                score = len(alias) + (300 - min(distance, 300)) + (start / max(len(joined), 1))
                candidates.append((score, code))

    if candidates:
        return max(candidates, key=lambda item: item[0])[1]

    for code in LANGUAGE_NAMES:
        if code == "und":
            continue
        if re.search(rf"(?<![a-z0-9]){re.escape(code)}(?![a-z0-9])", joined, re.IGNORECASE):
            return code
    return "und"


def _season_episode(value: str) -> tuple[Optional[int], Optional[int]]:
    match = _SEASON_EPISODE.search(value or "")
    if not match:
        return None, None
    season = match.group("s1") or match.group("s2") or match.group("s3")
    episode = match.group("e1") or match.group("e2") or match.group("e3")
    return int(season), int(episode)


def _strip_title_noise(value: str) -> str:
    """Return a clean media title from a noisy subtitle filename.

    Telegram subtitle names commonly use underscores, for example
    ``Drishyam_2_2021_Malayalam_HDRip_400MB_x264_AAC_sinhala_sub.srt``.
    An underscore is a regex *word* character, so technical-token expressions
    with ``\b`` boundaries cannot match until separators are normalised.
    Convert separators first; then remove years, codecs, sizes, languages, and
    subtitle labels. This keeps the actual title available for exact matching.
    """
    value = unicodedata.normalize("NFKC", value or "")
    value = _URL.sub(" ", value)
    # Do this before marker matching. Otherwise ``_HDRip_`` and ``_2021_``
    # never form word boundaries and leak into the parsed title.
    value = re.sub(r"[._\-]+", " ", value)
    value = _EXPLICIT_SUB_TAG.sub(" ", value)
    value = _IMDB_ID.sub(" ", value)
    value = _TMDB_ID.sub(" ", value)
    value = _SEASON_EPISODE.sub(" ", value)
    value = _YEAR.sub(" ", value)
    # Strip sizes and bitrates.  Keep ``bps`` / ``/s`` as part of the token:
    # ``192Kbps`` previously left ``192Kbps`` in titles because the old
    # ``\b...kb\b`` expression saw the trailing ``ps`` as a word suffix.
    value = re.sub(
        r"\b\d+(?:\.\d+)?\s*(?:k|m|g|t)(?:i)?b(?:ps|/?s)?\b",
        " ",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(r"\[[^\]]*\]|\([^)]*(?:sub|srt|ass|vtt)[^)]*\)", " ", value, flags=re.IGNORECASE)
    value = _TECHNICAL_MARKER.sub(" ", value)
    for aliases in LANGUAGE_ALIASES.values():
        for alias in aliases:
            value = _word_pattern(alias).sub(" ", value)
    value = re.sub(r"\b(?:sub|subtitle|subtitles|esub)\b", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" ._-[]()")
    return value


def parse_subtitle_identity(filename: str, caption: str = "") -> SubtitleIdentity:
    """Extract language and media hints from a subtitle document.

    Explicit tags are preferred: ``[SUB:tt1234567 si]`` and
    ``[SUB:tt1234567 S01E02 Sinhala]``. Filename-based matching is used when
    no explicit tag is present.
    """
    source_filename = (filename or "").strip()
    source_caption = (caption or "").strip()
    combined = " ".join(part for part in (source_caption, source_filename) if part)

    explicit = _EXPLICIT_SUB_TAG.search(combined)
    imdb_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    hint = "filename"
    explicit_tail = ""
    if explicit:
        hint = "explicit_tag"
        raw_id = explicit.group("id").replace(" ", "")
        explicit_tail = explicit.group("tail") or ""
        if raw_id.lower().startswith("tt"):
            imdb_id = raw_id.lower()
        else:
            raw_tmdb = re.search(r"\d+", raw_id)
            tmdb_id = int(raw_tmdb.group()) if raw_tmdb else None
    else:
        imdb_match = _IMDB_ID.search(combined)
        tmdb_match = _TMDB_ID.search(combined)
        imdb_id = imdb_match.group(1).lower() if imdb_match else None
        tmdb_id = int(tmdb_match.group(1)) if tmdb_match else None
        if imdb_id or tmdb_id:
            hint = "embedded_id"

    season, episode = _season_episode(f"{explicit_tail} {combined}")
    language_code = normalize_language(explicit_tail) if explicit_tail else "und"
    if language_code == "und":
        language_code = detect_language(explicit_tail, source_caption, source_filename)

    # Keep the release year separately.  It lets a short or numeric title such
    # as ``29 (2026).srt`` be linked safely without opening fuzzy matching to
    # unrelated one-word releases.
    release_year = None
    for year_source in (source_filename, source_caption):
        year_match = _YEAR.search(year_source or "")
        if year_match:
            release_year = int(year_match.group(1))
            break

    name_without_extension = str(PurePath(source_filename).with_suffix("")) if source_filename else source_caption
    title = _strip_title_noise(name_without_extension)
    if not title:
        title = _strip_title_noise(source_caption)

    return SubtitleIdentity(
        source_filename=source_filename or "subtitle" + extension_from_filename(source_caption),
        source_caption=source_caption,
        extension=extension_from_filename(source_filename or source_caption),
        language_code=language_code,
        language_name=language_name(language_code),
        imdb_id=imdb_id,
        tmdb_id=tmdb_id,
        title=title,
        normalized_title=normalize_title(title),
        release_year=release_year,
        season=season,
        episode=episode,
        match_hint=hint,
    )
