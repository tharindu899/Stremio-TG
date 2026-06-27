"""Pure parsing helpers for subtitle filenames and Telegram captions."""
from __future__ import annotations

import re
import unicodedata
from pathlib import PurePath
from typing import Optional

from Backend.helper.subtitle_constants import (
    DEFAULT_SUBTITLE_LANGUAGE,
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
    r"(?<![a-z0-9])(?:s(?P<s1>\d{1,2})[ ._\-]*e(?P<e1>\d{1,3})|"
    r"(?P<s2>\d{1,2})x(?P<e2>\d{1,3})|"
    r"season[ ._\-]*(?P<s3>\d{1,2})[ ._\-]*episode[ ._\-]*(?P<e3>\d{1,3}))(?![a-z0-9])",
    re.IGNORECASE,
)
_YEAR = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")
_URL = re.compile(r"\b(?:https?|ftp)://\S+", re.IGNORECASE)
_TECHNICAL_MARKER = re.compile(
    r"\b(?:2160p|1080p|720p|576p|480p|360p|4k|uhd|fhd|hdrip|webrip|web[ ._-]?dl|"
    r"bluray|bdrip|dvdrip|remux|x26[45]|hevc|avc|h\.?(?:264|265)|aac|ddp?\+?|"
    r"dts(?:[ ._-]?hd)?|truehd|atmos|proper|repack|extended|uncut|complete|hq|hq[ ._-]?hdrip|"
    r"esub|subtitle|subtitles|subs?|dubbed|dual|audio|stereo|mono|(?:2|5|7)[ .]?1|"
    r"\d{1,2}ch|(?:8|10|12)bit|hi10p|multi(?:sub)?|yts|rarbg)\b",
    re.IGNORECASE,
)
_SUBTITLE_MARKER = re.compile(
    r"\b(?:sub(?:title)?s?|srt|ass|ssa|vtt|cc|caption|esub)\b",
    re.IGNORECASE,
)
_RELEASE_SEPARATOR = re.compile(r"[\s._\-\[\](){}]+")

# Two-letter language codes are useful in release names (``720p.si.WEB-DL``),
# but are too ambiguous to trust everywhere.  They are handled separately from
# full language labels and accepted only in a credible subtitle/release context.
_LANGUAGE_CODES = tuple(code for code in LANGUAGE_NAMES if code != "und")
_LANGUAGE_CODE_PATTERN = re.compile(
    rf"(?<![a-z0-9])(?P<code>{'|'.join(re.escape(code) for code in _LANGUAGE_CODES)})(?![a-z0-9])",
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


def _nearest_marker_score(value: str, start: int, end: int) -> float:
    """Score proximity to an actual subtitle label, not only the file suffix."""
    best = 0.0
    for marker in _SUBTITLE_MARKER.finditer(value):
        marker_text = marker.group(0).casefold()
        distance = min(abs(start - marker.end()), abs(marker.start() - end))
        # ``srt``/``ass`` are weak evidence because every subtitle has an
        # extension.  ``sub``/``subtitle`` and ``esub`` are a much clearer
        # language-label context.
        weight = 95.0 if marker_text in {"srt", "ass", "ssa", "vtt"} else 420.0
        best = max(best, max(0.0, weight - min(float(distance), weight)))
    return best


def _release_context_score(value: str, start: int, end: int) -> float:
    """Recognize standard codec/source sandwiches around a short code."""
    before = value[:start].strip(" ._-[](){}")
    after = value[end:].strip(" ._-[](){}")
    previous = _RELEASE_SEPARATOR.split(before)[-1] if before else ""
    following = _RELEASE_SEPARATOR.split(after)[0] if after else ""
    # Do not count a bare subtitle extension as a release marker.  Otherwise a
    # trailing uploader/group suffix such as ``.Ms.srt`` becomes Malay.
    context = " ".join(token for token in (previous, following) if token.casefold() not in {"srt", "ass", "ssa", "vtt"})
    if not context:
        return 0.0
    return 430.0 if _TECHNICAL_MARKER.search(context) else 0.0


def _bracket_score(value: str, start: int, end: int) -> float:
    left = value[:start].rstrip()
    right = value[end:].lstrip()
    if left.endswith(("[", "(", "{")) and right.startswith(("]", ")", "}")):
        return 760.0
    return 0.0


def _terminal_extension_score(value: str, end: int) -> float:
    """Recognize ``.si.srt`` without trusting an arbitrary inner token."""
    tail = value[end:]
    if re.match(r"^[ ._\-]*(?:srt|ass|ssa|vtt|sub|smi|sami)\b", tail, re.IGNORECASE):
        return 165.0
    return 0.0


def detect_language(*values: str) -> str:
    """Detect the subtitle language without trusting arbitrary short tokens.

    Full labels such as ``Sinhala`` or ``Japanese`` are strong evidence.  ISO
    codes are accepted only when they appear in a release/subtitle context,
    which avoids treating a final release-group tag (for example ``Ms``) as a
    language.  This still supports common filenames such as
    ``Movie.2025.720p.si.WEB-DL.srt`` and ``Movie [si].srt``.
    """
    joined = " ".join(str(value or "") for value in values if value)
    if not joined:
        return "und"

    candidates: list[tuple[float, str]] = []
    length = max(len(joined), 1)

    # Written names and common aliases need some release/subtitle context too.
    # That avoids misreading a real title such as ``Hindi Medium`` as a Hindi
    # subtitle, while still accepting ``Movie.2025.Sinhala.srt`` and
    # ``Movie Japanese Sub.srt``.
    normalized_for_boundary = re.sub(r"[._\-]", " ", joined)
    release_boundary = _release_boundary(normalized_for_boundary)
    for code, aliases in LANGUAGE_ALIASES.items():
        for alias in aliases:
            for match in _word_pattern(alias).finditer(joined):
                start, end = match.span()
                marker_score = _nearest_marker_score(joined, start, end)
                context_score = _release_context_score(joined, start, end)
                bracket_score = _bracket_score(joined, start, end)
                suffix_score = _terminal_extension_score(joined, end)
                evidence = marker_score + context_score + bracket_score + suffix_score
                if evidence < 150.0:
                    continue
                # A language word before the release boundary is usually part
                # of the actual title unless it is explicitly beside ``sub``.
                if (
                    release_boundary is not None
                    and start < release_boundary
                    and marker_score < 200.0
                    and context_score == 0.0
                    and bracket_score == 0.0
                ):
                    continue
                score = 620.0 + min(len(alias) * 12.0, 180.0) + evidence
                score += (start / length) * 0.5
                candidates.append((score, code))

    # Standard language-code labels need additional proof.  A code beside a
    # source/codec marker or inside brackets is accepted; a stray two-letter
    # uploader suffix is not.
    for match in _LANGUAGE_CODE_PATTERN.finditer(joined):
        code = match.group("code").casefold()
        start, end = match.span()
        marker_score = _nearest_marker_score(joined, start, end)
        context_score = _release_context_score(joined, start, end)
        bracket_score = _bracket_score(joined, start, end)
        suffix_score = _terminal_extension_score(joined, end)
        score = marker_score + context_score + bracket_score + suffix_score
        if score < 150.0:
            continue
        # A code between recognised release tokens is the strongest generic
        # signal.  This makes ``720p.si.WEB-DL`` beat a final ``.Ms.srt``.
        score += 140.0 + (start / length) * 0.5
        candidates.append((score, code))

    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    return "und"


def _season_episode(value: str) -> tuple[Optional[int], Optional[int]]:
    match = _SEASON_EPISODE.search(value or "")
    if not match:
        return None, None
    season = match.group("s1") or match.group("s2") or match.group("s3")
    episode = match.group("e1") or match.group("e2") or match.group("e3")
    return int(season), int(episode)


def _release_boundary(value: str) -> int | None:
    """Find the first reliable point where a release name stops being a title."""
    boundaries: list[int] = []

    for match in _SEASON_EPISODE.finditer(value):
        if value[:match.start()].strip(" ._-"):
            boundaries.append(match.start())

    for match in _YEAR.finditer(value):
        prefix = value[:match.start()].strip(" ._-")
        # A four-digit movie title may be followed by the real release year,
        # such as ``1917.2019.1080p``.  Only use a year after some title text.
        if prefix:
            boundaries.append(match.start())

    for match in _TECHNICAL_MARKER.finditer(value):
        if value[:match.start()].strip(" ._-"):
            boundaries.append(match.start())

    return min(boundaries) if boundaries else None


def _strip_trailing_language(value: str, language_code: str) -> str:
    """Remove only a trailing language label, preserving titles like Hindi Medium."""
    language_code = normalize_language(language_code)
    candidates = list(LANGUAGE_ALIASES.get(language_code, ()))
    if language_code != "und":
        candidates.append(language_code)

    result = value.strip()
    for alias in sorted(candidates, key=len, reverse=True):
        pattern = re.compile(
            rf"(?:^|[\s._\-\[\](){{}}]){re.escape(alias)}$",
            re.IGNORECASE,
        )
        match = pattern.search(result)
        if match:
            result = result[:match.start()].strip(" ._-[](){}")
            break
    return result


def _strip_title_noise(value: str, language_code: str = "und") -> str:
    """Return the title portion of a noisy subtitle filename.

    The parser stops at the first release boundary instead of deleting tokens
    from the whole string.  That prevents source tags, codecs, uploader names,
    and short language codes from leaking into the search title.
    """
    value = unicodedata.normalize("NFKC", value or "")
    value = _URL.sub(" ", value)
    value = _EXPLICIT_SUB_TAG.sub(" ", value)
    value = _IMDB_ID.sub(" ", value)
    value = _TMDB_ID.sub(" ", value)
    value = re.sub(r"[._\-]+", " ", value)
    value = re.sub(r"\[[^\]]*\]", " ", value)
    value = re.sub(r"\([^)]*(?:sub|srt|ass|vtt)[^)]*\)", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" ._-[]()")

    boundary = _release_boundary(value)
    if boundary is not None:
        value = value[:boundary]

    # A subtitle without a year/quality marker may end in ``Sinhala Sub``.
    # The marker boundary leaves the language word behind, so trim it only
    # when it is the final release label.
    value = _strip_trailing_language(value, language_code)
    value = re.sub(r"\s+", " ", value).strip(" ._-[]()")
    return value


def parse_subtitle_identity(filename: str, caption: str = "") -> SubtitleIdentity:
    """Extract language and media hints from a subtitle document.

    Explicit tags are preferred: ``[SUB:tt1234567 si]`` and
    ``[SUB:tt1234567 S01E02 Sinhala]``. Filename-based matching is used when
    no explicit tag is present. Unlabelled subtitles default to Sinhala only
    after all filename and caption language checks fail.
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
    # Use Sinhala only as the final fallback. Explicit language labels found in
    # the tag, caption, or filename always take priority.
    if language_code == "und":
        language_code = DEFAULT_SUBTITLE_LANGUAGE

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
    title = _strip_title_noise(name_without_extension, language_code)
    if not title:
        title = _strip_title_noise(source_caption, language_code)

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
