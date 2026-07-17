import asyncio
import re
import traceback
from typing import Optional, List, Dict
from urllib.parse import quote

import PTN

import Backend
from Backend.config import Telegram
from Backend.logger import LOGGER
from Backend.helper.imdb import get_detail, get_season, search_title, search_title_multi
from Backend.helper.settings_manager import SettingsManager
from Backend.helper.encrypt import encode_string
from Backend.helper.split_files import (
    SplitFileInfo, detect_split_file, parse_split_info, parse_combined_episodes,
    strip_part_suffix, split_metadata_fields,
)
from Backend.helper.caption_tools import extract_supported_filename
from Backend.helper.anime import fetch_anime_metadata, fetch_anime_movie_metadata
from themoviedb import aioTMDb
from rapidfuzz import fuzz
from guessit import guessit as _guessit
from difflib import SequenceMatcher

#----- ── Config & caches ────────────────────────────────────────────────────────
_CINEMETA_THRESHOLD = 0.60
_TMDB_THRESHOLD = 0.55
_STRONG_MATCH = 0.92
_ALT_TITLE_LOOKUPS = 5

IMDB_CACHE: dict = {}
TMDB_SEARCH_CACHE: dict = {}
TMDB_DETAILS_CACHE: dict = {}
EPISODE_CACHE: dict = {}
ALT_TITLES_CACHE: dict = {}

API_SEMAPHORE = asyncio.Semaphore(12)

_INFLIGHT: Dict[tuple, asyncio.Future] = {}


async def _cached_call(store: dict, key, ns: str, producer):
    if key in store:
        return store[key]
    flight_key = (ns, key)
    fut = _INFLIGHT.get(flight_key)
    if fut is not None:
        return await fut
    fut = asyncio.get_running_loop().create_future()
    _INFLIGHT[flight_key] = fut
    try:
        result = await producer()
    except Exception as e:
        _INFLIGHT.pop(flight_key, None)
        if not fut.done():
            fut.set_exception(e)
            fut.exception()  #----- mark retrieved to silence asyncio warning when no waiters
        raise
    store[key] = result
    _INFLIGHT.pop(flight_key, None)
    if not fut.done():
        fut.set_result(result)
    return result

_MULTIPART_RE = re.compile(r"(?:part|cd|disc|disk)[s._-]*\d+(?=\.\w+$)", re.IGNORECASE)

#----- Combined files share one "Season N Combined" entry per real season, filed in
#----- the Specials folder (season 0).
COMBINED_SEASON = 0
COMBINED_EPISODE_BASE = 1000

_tmdb_client: aioTMDb | None = None
_tmdb_client_key: str | None = None


#----- ── TMDb client & image helpers ─────────────────────────────────────────────
def tmdb_api_key() -> str:
    try:
        key = SettingsManager.current().tmdb_api
        if key:
            return key
    except Exception:
        pass
    return getattr(Telegram, "TMDB_API", "") or ""


def get_tmdb_client() -> aioTMDb:
    global _tmdb_client, _tmdb_client_key
    current_key = tmdb_api_key()
    if _tmdb_client is None or _tmdb_client_key != current_key:
        _tmdb_client = aioTMDb(key=current_key, language="en-US", region="US")
        _tmdb_client_key = current_key
    return _tmdb_client


def format_tmdb_image(path: str, size="w500") -> str:
    return f"https://image.tmdb.org/t/p/{size}{path}" if path else ""


#----- Placeholder cover host. Only the path is stored, so this host can change any time.
GRADIENT_COVER_BASE = "https://gradient-cover-api.vercel.app"


#----- Relative gradient cover path persisted for titles without artwork
def gradient_cover_path(title: str, portrait: bool = False) -> str:
    path = f"/api/image?text={quote((title or 'Media').strip() or 'Media')}&badge="
    return f"{path}&orientation=portrait" if portrait else path


#----- Rebind a stored gradient cover (path or legacy full URL) to the current host
def resolve_cover_url(value: str) -> str:
    value = str(value or "")
    idx = value.find("/api/image?")
    return f"{GRADIENT_COVER_BASE}{value[idx:]}" if idx != -1 else value


def get_tmdb_logo(images) -> str:
    logos = getattr(images, "logos", None) if images else None
    if not logos:
        return ""
    for logo in logos:
        if getattr(logo, "iso_639_1", None) == "en" and getattr(logo, "file_path", None):
            return format_tmdb_image(logo.file_path, "w300")
    for logo in logos:
        if getattr(logo, "file_path", None):
            return format_tmdb_image(logo.file_path, "w300")
    return ""


def format_imdb_images(imdb_id: str) -> dict:
    if not imdb_id:
        return {"poster": "", "backdrop": "", "logo": ""}
    return {
        "poster": f"https://images.metahub.space/poster/small/{imdb_id}/img",
        "backdrop": f"https://images.metahub.space/background/medium/{imdb_id}/img",
        "logo": f"https://images.metahub.space/logo/medium/{imdb_id}/img",
    }


#----- ── ID & title helpers ──────────────────────────────────────────────────────
def extract_default_id(text: str) -> str | None:
    if not text:
        return None
    bare_imdb = re.search(r"\b(tt\d{7,10})\b", text)
    if bare_imdb:
        return bare_imdb.group(1)
    imdb_url = re.search(r"/title/(tt\d+)", text)
    if imdb_url:
        return imdb_url.group(1)
    tmdb_url = re.search(r"/(?:movie|tv)/(\d+)", text)
    if tmdb_url:
        return tmdb_url.group(1)
    return None


def _split_default_id(default_id) -> tuple[str | None, int | None, bool, bool]:
    if not default_id:
        return None, None, False, False
    value = str(default_id).strip()
    if value.startswith("tt"):
        return value, None, True, False
    if value.isdigit():
        return None, int(value), False, True
    return None, None, False, False


#----- Advanced title matching merged from TG-strimeo.
_ALIAS_STOPWORDS = {
    "a", "an", "and", "at", "by", "for", "from", "in", "of", "on", "or",
    "the", "to", "with", "my", "our", "your", "his", "her", "its", "new",
    "one", "part", "season", "series", "movie", "film",
}


def _title_tokens(title: str) -> list[str]:
    """Normalize a title into comparable words without losing joined aliases.

    Release names often omit punctuation from a registered title.  Splitting
    camel-case here makes `ReZero` and `Re:ZERO` comparable while remaining
    safe for ordinary titles.
    """
    if not title:
        return []
    value = str(title).strip()
    value = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", value)
    value = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", value)
    value = value.lower()
    value = re.sub(r"^\b(the|a|an)\b\s+", "", value)
    value = re.sub(r"[^\w\s]", " ", value)
    return [token for token in re.split(r"\s+", value) if token]


_ROMAN_ORDINALS = {
    "i": "1", "ii": "2", "iii": "3", "iv": "4", "v": "5",
    "vi": "6", "vii": "7", "viii": "8", "ix": "9", "x": "10",
    "xi": "11", "xii": "12", "xiii": "13", "xiv": "14", "xv": "15",
    "xvi": "16", "xvii": "17", "xviii": "18", "xix": "19", "xx": "20",
}
_ORDINAL_CONTEXT_TOKENS = {"part", "chapter", "episode", "season", "volume", "vol", "act"}


def _canonical_title_tokens(title: str) -> list[str]:
    """Normalize title-number spellings only where their context is explicit.

    Release titles often write sequel/part numbers as Roman numerals while
    provider metadata uses Arabic numerals.  Convert only after terms such as
    ``Part`` or ``Chapter`` so ordinary one-letter words are never rewritten.
    """
    tokens = _title_tokens(title)
    normalized: list[str] = []
    for index, token in enumerate(tokens):
        previous = tokens[index - 1] if index else ""
        if previous in _ORDINAL_CONTEXT_TOKENS and token in _ROMAN_ORDINALS:
            normalized.append(_ROMAN_ORDINALS[token])
        else:
            normalized.append(token)
    return normalized


def _normalize_title(title: str) -> str:
    """Lower-case, normalize punctuation and collapse whitespace."""
    return " ".join(_title_tokens(title))


def _canonical_normalize_title(title: str) -> str:
    """Normalize safe ordinal variants used by provider title matching."""
    return " ".join(_canonical_title_tokens(title))


def _leading_initialism_score(source_title: str, other_title: str) -> float:
    """Recognize a validated ``A.R.M. - Expanded Title`` alias pair.

    An initialism is trusted only when it appears at the beginning of the
    expanded release title *and* its letters exactly equal the initials of the
    remaining meaningful words.  This accepts titles such as ``A.R.M. -
    Ajayante Randam Moshanam`` ↔ ``A.R.M.`` without broadly accepting short,
    unrelated titles.
    """
    if not source_title or not other_title:
        return 0.0

    match = re.match(
        r"^\s*((?:[A-Za-z]\s*\.\s*){1,}[A-Za-z])(?=\s|[-:–—]|$)",
        str(source_title),
    )
    if not match:
        return 0.0

    initialism = re.sub(r"[^A-Za-z0-9]", "", match.group(1)).casefold()
    if len(initialism) < 2:
        return 0.0

    expansion = [
        token for token in _title_tokens(str(source_title)[match.end():])
        if token not in _ALIAS_STOPWORDS
    ]
    if len(expansion) < 2:
        return 0.0

    expansion_initials = "".join(token[0] for token in expansion)
    other_compact = "".join(_title_tokens(other_title))
    if initialism == expansion_initials and other_compact == initialism:
        return 0.98
    return 0.0


def _title_similarity(t1: str, t2: str) -> float:
    """Fuzzy similarity between two titles, 0–1."""
    n1, n2 = _normalize_title(t1), _normalize_title(t2)
    if not n1 or not n2:
        return 0.0

    scores = [
        SequenceMatcher(None, n1, n2).ratio(),
        # Joining tokens catches punctuation-only differences (`ReZero` vs
        # `Re:ZERO`) without broadly lowering the normal confidence threshold.
        SequenceMatcher(None, n1.replace(" ", ""), n2.replace(" ", "")).ratio(),
    ]

    # Safe sequel/part-number normalization: `Part I` ↔ `Part 1`.
    c1, c2 = _canonical_normalize_title(t1), _canonical_normalize_title(t2)
    if c1 and c2:
        scores.extend((
            SequenceMatcher(None, c1, c2).ratio(),
            SequenceMatcher(None, c1.replace(" ", ""), c2.replace(" ", "")).ratio(),
        ))

    # Abbreviation plus verified expanded-title form: `A.R.M.` ↔
    # `A.R.M. - Ajayante Randam Moshanam`.
    scores.append(_leading_initialism_score(t1, t2))
    scores.append(_leading_initialism_score(t2, t1))
    return max(scores)


def _cinemeta_title_compatible(query_title: str, result_title: str) -> bool:
    """Reject fuzzy Cinemeta lookalikes before their IMDb IDs are trusted.

    Character similarity alone can score unrelated titles surprisingly high,
    such as ``Demon Slayer`` versus ``Dragon Slayers``.  A wrong IMDb series
    can still contain the requested S/E number, so it must be rejected before
    episode lookup.  Formatting-only differences and a canonical title with a
    longer suffix remain valid (for example ``Demon Slayer`` →
    ``Demon Slayer: Kimetsu no Yaiba``).
    """
    query_norm = _canonical_normalize_title(query_title)
    result_norm = _canonical_normalize_title(result_title)
    if not query_norm or not result_norm:
        return False

    query_compact = query_norm.replace(" ", "")
    result_compact = result_norm.replace(" ", "")
    if query_compact == result_compact:
        return True

    if _leading_initialism_score(query_title, result_title) >= 0.95:
        return True

    query_tokens = [token for token in _canonical_title_tokens(query_title) if token not in _ALIAS_STOPWORDS]
    result_tokens = [token for token in _canonical_title_tokens(result_title) if token not in _ALIAS_STOPWORDS]
    if not query_tokens or not result_tokens:
        return False

    # A multi-word source title may be the leading part of an official title.
    # Never use this for one-word titles: e.g. "Avatar" is too ambiguous.
    if len(query_tokens) >= 2 and len(query_compact) >= 6:
        if query_compact in result_compact or result_compact in query_compact:
            return True

    query_unique = set(query_tokens)
    result_unique = set(result_tokens)
    shared = query_unique & result_unique
    if len(query_unique) >= 2 and shared:
        coverage = len(shared) / len(query_unique)
        has_distinctive_word = any(len(token) >= 4 for token in shared)
        if coverage >= 0.80 and has_distinctive_word:
            return True

    return False


def _leading_alias_anchor(query_title: str, result_title: str) -> bool:
    """Return True for a narrow, reliable translated-title anchor match.

    Some APIs return an English official title for a release filename that
    uses its long romanized title.  A general low threshold would create bad
    matches, so this fallback is intentionally strict:
      * it is used only for TV searches;
      * the source title must contain at least four words;
      * the first two meaningful words must be an exact prefix of the result;
      * together those words must be distinctive enough.

    Example: `ReZero kara Hajimeru Isekai Seikatsu` →
    `Re:ZERO -Starting Life in Another World-`.
    """
    query_tokens = [t for t in _title_tokens(query_title) if t not in _ALIAS_STOPWORDS]
    result_tokens = [t for t in _title_tokens(result_title) if t not in _ALIAS_STOPWORDS]
    if len(query_tokens) < 4 or len(result_tokens) < 2:
        return False
    anchor = query_tokens[:2]
    if len("".join(anchor)) < 5:
        return False
    return result_tokens[:2] == anchor


def _result_titles(item, type_: str) -> list[str]:
    """Return every title field exposed by a TMDb search result."""
    primary = "title" if type_ == "movie" else "name"
    original = "original_title" if type_ == "movie" else "original_name"
    values = [getattr(item, primary, "") or "", getattr(item, original, "") or ""]
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = str(value).strip()
        if normalized and normalized.casefold() not in seen:
            seen.add(normalized.casefold())
            result.append(normalized)
    return result


def _year_from_str(year_val) -> int:
    if not year_val:
        return 0
    m = re.search(r"(\d{4})", str(year_val))
    return int(m.group(1)) if m else 0


def _score_candidate(
    query_title: str,
    query_year: Optional[int],
    result_title: str,
    result_year: int,
    year_reliable: bool = True,
    year_lower_bound: bool = False,
) -> float:
    score = _title_similarity(query_title, result_title)
    if score < 0.5:
        return score

    if query_year and result_year:
        if year_lower_bound:
            if int(query_year) >= result_year and score >= 0.80:
                score += 0.15 / (1 + (int(query_year) - result_year) * 0.1)
            return score
        diff = abs(int(query_year) - result_year)
        if year_reliable:
            if diff > 2:
                score = max(0.0, score - 0.10 * (diff - 2))
            elif score >= 0.80:
                if diff == 0:
                    score = min(1.0, score + 0.20)
                elif diff == 1:
                    score = min(1.0, score + 0.07)
        elif diff == 0 and score >= 0.80:
            score = min(1.0, score + 0.05)
    elif query_year and year_reliable and not year_lower_bound:
        score = max(0.0, score - 0.20)
    return score


def _build_query_variants(title: str, year: Optional[int] = None) -> List[str]:
    variants: List[str] = [title]
    if year:
        variants.append(f"{title} {year}")

    stripped = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", title)).strip()
    if stripped and stripped.lower() != title.lower():
        variants.append(stripped)
        if year:
            variants.append(f"{stripped} {year}")

    no_article = re.sub(r"^\b(the|a|an)\b\s+", "", title, flags=re.IGNORECASE).strip()
    if no_article and no_article.lower() != title.lower():
        variants.append(no_article)

    seen: set = set()
    ordered: List[str] = []
    for v in variants:
        key = v.lower()
        if v and key not in seen:
            seen.add(key)
            ordered.append(v)
    return ordered


def _first(value):
    return value[0] if isinstance(value, list) else value


#----- ── Filename parsing ────────────────────────────────────────────────────────
def parse_media_name(name: str) -> dict:
    try:
        ptn = PTN.parse(name) or {}
    except Exception as e:
        LOGGER.warning(f"PTN parsing failed for {name}: {e}")
        ptn = {}

    parsed = {
        "title": ptn.get("title"),
        "year": ptn.get("year"),
        "season": ptn.get("season"),
        "episode": ptn.get("episode"),
        "quality": ptn.get("resolution"),
        "excess": ptn.get("excess"),
    }

    if _guessit:
        try:
            g = _guessit(name)
            parsed["title"] = parsed["title"] or _first(g.get("title"))
            parsed["year"] = parsed["year"] or _first(g.get("year"))
            parsed["season"] = parsed["season"] or _first(g.get("season"))
            parsed["episode"] = parsed["episode"] or _first(g.get("episode"))
            parsed["quality"] = parsed["quality"] or _first(g.get("screen_size"))
        except Exception as e:
            LOGGER.warning(f"GuessIt parsing failed for {name}: {e}")

    return parsed


def _infer_quality_from_name(name: str) -> str | None:
    """Best-effort quality label; metadata indexing must not require one."""
    match = re.search(
        r"(?<!\d)(2160|1440|1080|720|576|540|480|360)(?:p|i)?(?!\d)",
        str(name or ""),
        flags=re.IGNORECASE,
    )
    if match:
        return f"{match.group(1)}p"
    if re.search(r"\b(?:4k|uhd)\b", str(name or ""), flags=re.IGNORECASE):
        return "2160p"
    if re.search(r"\bfhd\b", str(name or ""), flags=re.IGNORECASE):
        return "1080p"
    return None


_RELEASE_GROUP_PREFIX_RE = re.compile(r"^\s*(?:\[[^\]\r\n]{1,96}\]\s*)+")
# The episode number must be followed by a true release boundary.  This avoids
# treating titles such as ``Part 2`` as episodes while accepting normal fansub
# tails such as ``[1080p]``, ``WEB-DL`` or ``x265`` after a bare number.
_BARE_EPISODE_RELEASE_HEAD_RE = re.compile(
    r"""(?ix)
    ^\s*(?P<title>.+?)\s*[-–—]\s*(?P<episode>\d{1,4})
    (?=\s*(?:
        $|[-–—]|\[|\(|
        v\d+\b|\d{3,4}p\b|
        (?:web[ ._-]?(?:dl|rip)|blu[ ._-]?ray|b[dr]rip|hdrip|remux|dvdrip)\b|
        (?:x26[45]|h[ ._-]?26[45]|hevc|av1|aac|ddp?|dts|truehd|flac)\b
    ))
    """
)
_RELEASE_TECHNICAL_TAIL_RE = re.compile(
    r"""(?ix)
    (?:[.\s_-]+(?:
        v\d+|\d{3,4}p|web[ ._-]?(?:dl|rip)|blu[ ._-]?ray|b[dr]rip|hdrip|remux|dvdrip|
        x26[45]|h[ ._-]?26[45]|hevc|av1|aac|ddp?|dts|truehd|flac|multi|dual|10bit|8bit
    ))+\s*$
    """
)
_RELEASE_TRAILING_TAG_RE = re.compile(r"\s*\[(?P<tag>[^\]\r\n]{1,160})\]\s*$")
_RELEASE_TAG_TECHNICAL_RE = re.compile(
    r"(?ix)\b(?:v\d+|\d{3,4}p|web[ ._-]?(?:dl|rip)|blu[ ._-]?ray|b[dr]rip|hdrip|remux|dvdrip|x26[45]|h[ ._-]?26[45]|hevc|av1|aac|ddp?|dts|truehd|flac|multi|dual|10bit|8bit)\b"
)

# PTN occasionally infers S01E01 from incomplete audio/release tails such as
# ``... - x264 - (DD+``. A title is only treated as a regular TV episode when
# the filename itself contains a real season/episode marker. Bare-number anime
# releases are handled separately by ``_release_episode_parts`` below.
_EXPLICIT_EPISODE_MARKER_RE = re.compile(
    r"""(?ix)
    (?<![A-Za-z0-9])
    (?:
        S(?:eason)?\s*0*\d{1,3}\s*[-_. ]*E(?:pisode)?\s*0*\d{1,4}
        |\d{1,3}\s*[xX]\s*\d{1,4}
        |season\s*\d{1,3}\s*(?:episode|ep)\s*\d{1,4}
        |(?:episode|ep)\s*\d{1,4}
    )
    (?![A-Za-z0-9])
    """
)

# A standalone release year is a strong movie signal when a caption/filename
# has no real season/episode marker.  This protects movie captions such as
# ``Karakkam (2026) Malayalam`` from parser-generated ``S01E01`` values.
# Explicit episode tags always win, so ``Show (2026) S01E01`` remains TV.
_RELEASE_YEAR_RE = re.compile(r"(?<!\d)((?:19|20)\d{2})(?!\d)")

# Release labels that never belong to a movie/series title when they appear at
# the end of the pre-codec filename segment. This is used only after a parser
# episode result has been rejected as unverified.
_RELEASE_TITLE_BOUNDARY_RE = re.compile(
    r"""(?ix)
    (?:^|[\s._-])
    (?:
        \d{3,4}p|web[ ._-]?(?:dl|rip)|blu[ ._-]?ray|b[dr]rip|hdrip|
        remux|dvdrip|hdtv|x26[45]|h[ ._-]?26[45]|hevc|av1|aac|ddp?|dts|
        truehd|flac|atmos|eac3|esub|webmux
    )\b
    """
)
_RELEASE_TITLE_TRAILING_LABEL_RE = re.compile(
    r"""(?ix)
    (?:[\s._-]+(?:
        arabic|bangla|bengali|chinese|english|french|german|hindi|italian|
        japanese|kannada|korean|malayalam|polish|portuguese|russian|sinhala|
        spanish|tamil|telugu|turkish|urdu|hq|proper|internal|multi|dual|
        dubbed|sub(?:title)?s?|esub
    ))+\s*$
    """
)


def _has_explicit_episode_marker(filename: str) -> bool:
    raw = re.sub(
        r"(?i)\.(?:mkv|mp4|avi|ts|m4v|mov|wmv|webm|flv|m2ts|mpeg|mpg)$",
        "",
        str(filename or ""),
    )
    return bool(_EXPLICIT_EPISODE_MARKER_RE.search(raw))


def _release_year_from_source(value: str) -> Optional[int]:
    """Extract a plausible standalone release year from a caption/filename."""
    for match in _RELEASE_YEAR_RE.finditer(str(value or "")):
        try:
            year = int(match.group(1))
        except (TypeError, ValueError):
            continue
        if 1900 <= year <= 2099:
            return year
    return None


def _release_title_candidate(filename: str, fallback: str | None, year: Optional[int]) -> str:
    """Recover a clean provider-search title after an unverified PTN episode.

    The original parsed title is preserved as the fallback. The release prefix
    is trimmed only at an unmistakable technical boundary, then trailing
    language/source labels and the detected bracketed year are removed.
    """
    raw = re.sub(
        r"(?i)\.(?:mkv|mp4|avi|ts|m4v|mov|wmv|webm|flv|m2ts|mpeg|mpg)$",
        "",
        str(filename or ""),
    )
    boundary = _RELEASE_TITLE_BOUNDARY_RE.search(raw)
    if boundary:
        raw = raw[:boundary.start()]

    if year:
        raw = re.sub(
            rf"[\(\[]\s*{re.escape(str(year))}\s*[\)\]]",
            " ",
            raw,
            count=1,
        )

    raw = raw.replace("_", " ").replace(".", " ")
    raw = _RELEASE_TITLE_TRAILING_LABEL_RE.sub("", raw)
    raw = re.sub(r"[\[\]{}()]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip(" .-_–—")
    return raw or str(fallback or "").strip()


def _trim_release_episode_tail(value: str) -> str:
    """Remove only technical suffixes from an episode-name tail."""
    value = str(value or "").strip(" .-_–—")
    while value:
        match = _RELEASE_TRAILING_TAG_RE.search(value)
        if not match or not _RELEASE_TAG_TECHNICAL_RE.search(match.group("tag") or ""):
            break
        value = value[:match.start()].strip(" .-_–—")
    return _RELEASE_TECHNICAL_TAIL_RE.sub("", value).strip(" .-_–—")


def _release_episode_parts(filename: str, parsed: dict) -> tuple[Optional[str], Optional[int], Optional[str]]:
    """Recover bare-number anime releases without confusing them with splits.

    Supports forms such as ``[Judas] One Piece - 1101 [1080p].mkv`` and
    ``[Anime Time] Naruto - 035 - Episode name.mkv``.  A leading group tag is
    ignored; trailing release tags are tolerated.  Years and explicit
    ``Part/CD/Disc`` labels remain non-episode media.
    """
    raw = str(filename or "").strip()
    raw = re.sub(r"(?i)\.(?:mkv|mp4|avi|ts|m4v|mov|wmv|webm|flv|m2ts|mpeg|mpg)$", "", raw)
    raw = _RELEASE_GROUP_PREFIX_RE.sub("", raw).strip()
    if not raw:
        return None, None, None

    match = _BARE_EPISODE_RELEASE_HEAD_RE.match(raw)
    if not match:
        return None, None, None

    title = (match.group("title") or "").strip(" .-_–—")
    try:
        episode = int(match.group("episode") or "")
    except (TypeError, ValueError):
        return None, None, None

    # Four-digit years must stay movies, not become e.g. S01E2024.
    if not title or episode <= 0 or 1900 <= episode <= 2199:
        return None, None, None
    if re.search(r"(?i)\b(?:part|pt|cd|disc|disk)\s*$", title):
        return None, None, None

    tail = raw[match.end():].strip()
    # ``Movie - 1 (2026)`` is a common title/year form, not an episode.
    if re.match(r"^\(\s*(?:19|20)\d{2}\s*\)", tail):
        return None, None, None
    episode_title = None
    if tail.startswith(("-", "–", "—")):
        episode_title = _trim_release_episode_tail(tail[1:]) or None
    return title, episode, episode_title


def _episode_video_candidates(videos) -> list[tuple[int, int, dict]]:
    """Return regular provider episodes in stable chronological order."""
    candidates: list[tuple[int, int, dict]] = []
    for video in videos or []:
        if not isinstance(video, dict):
            continue
        try:
            season = int(video.get("season"))
            episode = int(video.get("episode"))
        except (TypeError, ValueError):
            continue
        if season < 1 or episode < 1:
            continue
        candidates.append((season, episode, video))

    # Cinemeta provides release dates for normal episodes.  Sorting by date
    # turns absolute anime numbering into the correct provider S/E pair while
    # falling back to season/episode when a date is absent.
    return sorted(
        candidates,
        key=lambda item: (
            str(item[2].get("released") or "9999-99-99"),
            item[0],
            item[1],
        ),
    )


def _map_absolute_episode(imdb_tv: dict | None, absolute_episode: Optional[int], episode_hint: Optional[str] = None) -> tuple[int, int] | None:
    """Map a release's absolute anime episode number to Cinemeta season/episode.

    Exact episode-title matches win.  For concise releases such as
    ``One Piece - 658.mkv`` without an episode title, use the provider's
    chronological regular-episode list.  Specials are excluded.
    """
    if not imdb_tv or not absolute_episode or absolute_episode < 1:
        return None

    candidates = _episode_video_candidates(imdb_tv.get("videos"))
    if not candidates:
        return None

    hint = str(episode_hint or "").strip()
    if hint:
        hint_norm = _canonical_normalize_title(hint)
        best: tuple[float, int, int] | None = None
        for season, episode, video in candidates:
            video_title = str(video.get("title") or "")
            score = _title_similarity(hint, video_title)
            if hint_norm and hint_norm == _canonical_normalize_title(video_title):
                score = 1.0
            if best is None or score > best[0]:
                best = (score, season, episode)
        if best and best[0] >= 0.92:
            return best[1], best[2]

    # The absolute number is one-based.  Protect against a partial provider
    # catalogue rather than silently mapping beyond the available series.
    if absolute_episode <= len(candidates):
        season, episode, _ = candidates[absolute_episode - 1]
        return season, episode
    return None



# OVA/OAD/Special/Extra names without S00E00 are filed under season 0.
_SPECIAL_EPISODE_RE = re.compile(
    r"""(?ix)^(?P<title>.*?)\b(?:OVA|OAD|SPECIAL|EXTRA|SP)\b
    [\s._-]*(?:E|EP|EPISODE)?[\s._-]*0*(?P<episode>\d{1,3})?\b"""
)


def _special_episode_parts(filename: str) -> tuple[Optional[str], Optional[int]]:
    raw = re.sub(
        r"(?i)\.(?:mkv|mp4|avi|ts|m4v|mov|wmv|webm|flv|m2ts|mpeg|mpg)$",
        "",
        str(filename or "").strip(),
    )
    match = _SPECIAL_EPISODE_RE.search(raw)
    if not match:
        return None, None
    title = re.sub(r"[._]+", " ", match.group("title") or "").strip(" .-_–—")
    if not title:
        return None, None
    return title, int(match.group("episode") or 1)

def _apply_combined_override(payload: dict, combined: dict) -> None:
    season, start, end = combined["season"], combined["start"], combined["end"]
    payload["season_number"] = COMBINED_SEASON
    payload["episode_number"] = COMBINED_EPISODE_BASE + season
    payload["episode_title"] = f"Season {season} Combined"
    label = "Full" if start is None else f"E{start:02d}-E{end:02d}"
    payload["quality"] = f"{payload.get('quality') or 'HD'} {label}"
    if not payload.get("episode_backdrop"):
        payload["episode_backdrop"] = payload.get("backdrop") or payload.get("poster") or ""


#----- ── Search (Cinemeta / TMDb) ────────────────────────────────────────────────
async def safe_imdb_search(title: str, type_: str, year: Optional[int] = None) -> str | None:
    is_tv = type_ != "movie"
    search_year = None if is_tv else year
    cache_key = f"imdb::{type_}::{title}::{year}"

    async def _produce():
        query_variants = _build_query_variants(title, search_year)
        best_id: str | None = None
        best_score = 0.0
        best_title = ""
        year_reliable = not is_tv

        for query in query_variants:
            try:
                async with API_SEMAPHORE:
                    results = await search_title_multi(query=query, type=type_, limit=8)
                for r in results:
                    score = _score_candidate(
                        title, year, r.get("title", ""), _year_from_str(r.get("year", "")),
                        year_reliable=year_reliable, year_lower_bound=is_tv,
                    )
                    if is_tv and not _cinemeta_title_compatible(title, r.get("title", "")):
                        score = min(score, 0.49)
                    if score > best_score:
                        best_score, best_id, best_title = score, r.get("id"), r.get("title", "")
                    if not is_tv and best_score >= _STRONG_MATCH:
                        break
            except Exception as e:
                LOGGER.warning(f"Cinemeta search variant '{query}' [{type_}] failed: {e}")
            if not is_tv and best_score >= _STRONG_MATCH:
                break

        if best_score >= _CINEMETA_THRESHOLD and best_id:
            LOGGER.info(f"Cinemeta match: '{title}' (year={year}) -> '{best_title}' [{best_id}] (score={best_score:.2f})")
            return best_id

        if best_id:
            LOGGER.info(
                f"Cinemeta low-confidence for '{title}' (year={year}, type={type_}) | "
                f"best '{best_title}' [{best_id}] score={best_score:.2f} -> falling back to TMDb"
            )
        else:
            LOGGER.info(f"Cinemeta returned no results for '{title}' (year={year}, type={type_}) -> falling back to TMDb")
        return None

    return await _cached_call(IMDB_CACHE, cache_key, "imdb_search", _produce)


async def _tmdb_raw_search(title: str, media_type: str, year: Optional[int]):
    client = get_tmdb_client()
    async with API_SEMAPHORE:
        if media_type == "movie":
            results = await (client.search().movies(query=title, year=year) if year else client.search().movies(query=title))
            if not results and year:
                results = await client.search().movies(query=title)
            return results
        return await client.search().tv(query=title)


async def safe_tmdb_search(title: str, type_: str, year: Optional[int] = None):
    is_tv = type_ != "movie"
    search_year = None if is_tv else year
    cache_key = f"tmdb_search::{type_}::{title}::{year}"

    async def _produce():
        try:
            results = await _tmdb_raw_search(title, type_, search_year)
            best = await _pick_best_tmdb_result(results, title, year, type_)
            if best is None and results:
                top = results[0]
                top_title = getattr(top, "title" if type_ == "movie" else "name", "?")
                LOGGER.info(f"TMDb '{title}' (year={year}) top result '{top_title}' did not meet threshold")
            return best
        except Exception as e:
            LOGGER.error(f"TMDb search failed for '{title}' [{type_}]: {e}")
            return None

    return await _cached_call(TMDB_SEARCH_CACHE, cache_key, "tmdb_search", _produce)


def _tmdb_title_year(item, media_type: str) -> tuple[str, int]:
    if media_type == "movie":
        date = getattr(item, "release_date", None)
        return getattr(item, "title", "") or "", getattr(date, "year", 0) if date else 0
    date = getattr(item, "first_air_date", None)
    return getattr(item, "name", "") or "", getattr(date, "year", 0) if date else 0


async def _pick_best_tmdb_result(results, query_title: str, query_year: Optional[int], media_type: str):
    if not results:
        return None

    year_reliable = media_type == "movie"
    year_lower_bound = not year_reliable
    scored = []
    best_item, best_score = None, 0.0
    for item in results:
        r_title, r_year = _tmdb_title_year(item, media_type)
        score = _score_candidate(query_title, query_year, r_title, r_year, year_reliable=year_reliable, year_lower_bound=year_lower_bound)
        scored.append((score, item, r_year))
        if score > best_score:
            best_score, best_item = score, item

    if best_score >= _STRONG_MATCH:
        return best_item

    scored.sort(key=lambda x: x[0], reverse=True)
    for _, item, r_year in scored[:_ALT_TITLE_LOOKUPS]:
        alt_titles = await _tmdb_alternative_titles(media_type, getattr(item, "id", None))
        for alt in alt_titles:
            alt_score = _score_candidate(query_title, query_year, alt, r_year, year_reliable=year_reliable, year_lower_bound=year_lower_bound)
            if alt_score > best_score:
                best_score, best_item = alt_score, item
                if best_score >= _STRONG_MATCH:
                    break
        if best_score >= _STRONG_MATCH:
            break

    return best_item if best_score >= _TMDB_THRESHOLD and best_item is not None else None


async def _tmdb_alternative_titles(media_type: str, tmdb_id) -> list[str]:
    if not tmdb_id:
        return []
    cache_key = (media_type, tmdb_id)

    async def _produce():
        titles: list[str] = []
        try:
            client = get_tmdb_client()
            async with API_SEMAPHORE:
                target = client.movie(tmdb_id) if media_type == "movie" else client.tv(tmdb_id)
                alt = await target.alternative_titles()
            entries = list(getattr(alt, "titles", None) or []) + list(getattr(alt, "results", None) or [])
            titles = [t for t in (getattr(e, "title", "") for e in entries) if t]
        except Exception as e:
            LOGGER.warning(f"TMDb alternative-titles fetch failed for {media_type} id={tmdb_id}: {e}")
        return titles

    return await _cached_call(ALT_TITLES_CACHE, cache_key, "alt_titles", _produce)


#----- ── Detail fetchers ─────────────────────────────────────────────────────────
async def _tmdb_details(media_type: str, item_id):
    cache_key = (media_type, item_id)

    async def _produce():
        try:
            client = get_tmdb_client()
            async with API_SEMAPHORE:
                target = client.movie(item_id) if media_type == "movie" else client.tv(item_id)
                details = await target.details(append_to_response="external_ids,credits")
                details.images = await target.images()
            return details
        except Exception as e:
            LOGGER.warning(f"TMDb {media_type} details fetch failed for id={item_id}: {e}")
            return None

    return await _cached_call(TMDB_DETAILS_CACHE, cache_key, "tmdb_details", _produce)


async def _tmdb_episode_details(tv_id, season, episode):
    key = (tv_id, season, episode)

    async def _produce():
        try:
            async with API_SEMAPHORE:
                return await get_tmdb_client().episode(tv_id, season, episode).details()
        except Exception:
            return None

    return await _cached_call(EPISODE_CACHE, key, "tmdb_ep", _produce)


async def _cached_imdb_detail(imdb_id: str, media_type: str):
    async def _produce():
        async with API_SEMAPHORE:
            return await get_detail(imdb_id=imdb_id, media_type=media_type)

    return await _cached_call(IMDB_CACHE, imdb_id, "imdb_detail", _produce)


async def _cached_imdb_season(imdb_id: str, season, episode):
    key = f"{imdb_id}::{season}::{episode}"

    async def _produce():
        async with API_SEMAPHORE:
            return await get_season(imdb_id=imdb_id, season_id=season, episode_id=episode)

    return await _cached_call(EPISODE_CACHE, key, "imdb_season", _produce)


async def _tmdb_external_imdb_id(media_type: str, tmdb_id) -> str | None:
    try:
        details = await _tmdb_details(media_type, tmdb_id)
        ext = getattr(details, "external_ids", None) if details else None
        return getattr(ext, "imdb_id", None) if ext else None
    except Exception:
        return None


#----- ── Payload builders ────────────────────────────────────────────────────────
def _extract_cast(details) -> list:
    credits = getattr(details, "credits", None) or {}
    cast = getattr(credits, "cast", []) or []
    return [getattr(c, "name", None) or getattr(c, "original_name", None) for c in cast]


def _tmdb_country_codes(details) -> list:
    codes: list = []
    for code in (getattr(details, "origin_country", None) or []):
        if code and code not in codes:
            codes.append(code)
    for country in (getattr(details, "production_countries", None) or []):
        code = getattr(country, "iso_3166_1", None) or (country.get("iso_3166_1") if isinstance(country, dict) else None)
        if code and code not in codes:
            codes.append(code)
    return codes


def _format_runtime(minutes) -> str:
    return f"{minutes} min" if minutes else ""


def _build_tmdb_movie_payload(movie, quality, encoded_string) -> dict:
    release = getattr(movie, "release_date", None)
    return {
        "tmdb_id": movie.id,
        "imdb_id": getattr(getattr(movie, "external_ids", None), "imdb_id", None),
        "title": movie.title,
        "year": getattr(release, "year", 0) if release else 0,
        "rate": getattr(movie, "vote_average", 0) or 0,
        "description": movie.overview or "",
        "poster": format_tmdb_image(movie.poster_path),
        "backdrop": format_tmdb_image(movie.backdrop_path, "original"),
        "logo": get_tmdb_logo(getattr(movie, "images", None)),
        "cast": _extract_cast(movie),
        "runtime": str(_format_runtime(getattr(movie, "runtime", None))),
        "media_type": "movie",
        "genres": [g.name for g in (movie.genres or [])],
        "original_language": getattr(movie, "original_language", None),
        "origin_country": _tmdb_country_codes(movie),
        "quality": quality,
        "encoded_string": encoded_string,
    }


def _build_tmdb_tv_payload(tv, ep, season, episode, quality, encoded_string) -> dict:
    first_air = getattr(tv, "first_air_date", None)
    series_runtime = tv.episode_run_time[0] if getattr(tv, "episode_run_time", None) else None
    runtime = _format_runtime((getattr(ep, "runtime", None) if ep else None) or series_runtime)
    fallback_ep_title = f"S{season:02d}E{episode:02d}"
    return {
        "tmdb_id": tv.id,
        "imdb_id": getattr(getattr(tv, "external_ids", None), "imdb_id", None),
        "title": tv.name,
        "year": getattr(first_air, "year", 0) if first_air else 0,
        "rate": getattr(tv, "vote_average", 0) or 0,
        "description": tv.overview or "",
        "poster": format_tmdb_image(tv.poster_path),
        "backdrop": format_tmdb_image(tv.backdrop_path, "original"),
        "logo": get_tmdb_logo(getattr(tv, "images", None)),
        "genres": [g.name for g in (tv.genres or [])],
        "media_type": "tv",
        "cast": _extract_cast(tv),
        "runtime": str(runtime),
        "original_language": getattr(tv, "original_language", None),
        "origin_country": _tmdb_country_codes(tv),
        "season_number": season,
        "episode_number": episode,
        "episode_title": getattr(ep, "name", fallback_ep_title) if ep else fallback_ep_title,
        "episode_backdrop": format_tmdb_image(getattr(ep, "still_path", None), "original") if ep else "",
        "episode_overview": getattr(ep, "overview", "") if ep else "",
        "episode_released": ep.air_date.strftime("%Y-%m-%dT05:00:00.000Z") if (ep and getattr(ep, "air_date", None)) else "",
        "quality": quality,
        "encoded_string": encoded_string,
    }


def _build_imdb_movie_payload(imdb, imdb_id, title, quality, encoded_string) -> dict:
    images = format_imdb_images(imdb_id)
    return {
        "tmdb_id": imdb.get("moviedb_id") or (imdb_id.replace("tt", "") if imdb_id else None),
        "imdb_id": imdb_id,
        "title": imdb.get("title", title),
        "year": imdb.get("releaseDetailed", {}).get("year", 0),
        "rate": imdb.get("rating", {}).get("star", 0),
        "description": imdb.get("plot", ""),
        "poster": images["poster"],
        "backdrop": images["backdrop"],
        "logo": images["logo"],
        "cast": imdb.get("cast", []),
        "runtime": str(imdb.get("runtime") or ""),
        "media_type": "movie",
        "genres": imdb.get("genre", []),
        "quality": quality,
        "encoded_string": encoded_string,
    }


def _build_imdb_tv_payload(imdb, ep, imdb_id, title, season, episode, quality, encoded_string) -> dict:
    images = format_imdb_images(imdb_id)
    return {
        "tmdb_id": imdb.get("moviedb_id") or (imdb_id.replace("tt", "") if imdb_id else None),
        "imdb_id": imdb_id,
        "title": imdb.get("title", title),
        "year": imdb.get("releaseDetailed", {}).get("year", 0),
        "rate": imdb.get("rating", {}).get("star", 0),
        "description": imdb.get("plot", ""),
        "poster": images["poster"],
        "backdrop": images["backdrop"],
        "logo": images["logo"],
        "cast": imdb.get("cast", []),
        "runtime": str(imdb.get("runtime") or ""),
        "genres": imdb.get("genre", []),
        "media_type": "tv",
        "season_number": season,
        "episode_number": episode,
        "episode_title": ep.get("title", f"S{season:02d}E{episode:02d}"),
        "episode_backdrop": ep.get("image", ""),
        "episode_overview": ep.get("plot", ""),
        "episode_released": str(ep.get("released", "")),
        "quality": quality,
        "encoded_string": encoded_string,
    }


#----- ── Anime helpers ───────────────────────────────────────────────────────────
def _is_anime_channel(channel) -> bool:
    anime_channels = SettingsManager.current().anime_channels
    if not anime_channels:
        return False
    target = str(channel).replace("-100", "")
    return any(str(c).strip().replace("-100", "") == target for c in anime_channels)


async def _enrich_anime_tv_artwork(result: dict, season: int, episode: int) -> dict:
    """Fill missing AniList/ani.zip artwork from Cinemeta/MetaHub.

    ani.zip does not provide an image for every absolute episode, especially
    long-running shows with episode numbers above 100.  The anime match itself
    is still valid, so missing artwork must not force a different metadata ID.
    """
    imdb_id = str(result.get("imdb_id") or "").strip()
    if not imdb_id:
        return result

    provider = None
    provider_episode = None
    try:
        provider = await _cached_imdb_detail(imdb_id, "tvSeries")
    except Exception as exc:
        LOGGER.debug("[ANIME] Cinemeta artwork lookup failed for %s: %s", imdb_id, exc)
    try:
        provider_episode = await _cached_imdb_season(imdb_id, season, episode)
    except Exception as exc:
        LOGGER.debug(
            "[ANIME] Cinemeta episode artwork lookup failed for %s S%02dE%02d: %s",
            imdb_id,
            season,
            episode,
            exc,
        )

    images = format_imdb_images(imdb_id)
    provider = provider or {}
    provider_episode = provider_episode or {}

    result["poster"] = (
        result.get("poster")
        or provider.get("poster")
        or images.get("poster")
        or ""
    )
    result["backdrop"] = (
        result.get("backdrop")
        or provider.get("background")
        or images.get("backdrop")
        or result.get("poster")
        or ""
    )
    result["logo"] = (
        result.get("logo")
        or provider.get("logo")
        or images.get("logo")
        or ""
    )

    # Keep ani.zip's episode data when present, but backfill the fields it
    # commonly omits on high absolute episode numbers and season-zero OVAs.
    result["episode_title"] = (
        result.get("episode_title")
        or provider_episode.get("title")
        or f"S{season:02d}E{episode:02d}"
    )
    result["episode_backdrop"] = (
        result.get("episode_backdrop")
        or provider_episode.get("image")
        or result.get("backdrop")
        or result.get("poster")
        or ""
    )
    result["episode_overview"] = (
        result.get("episode_overview")
        or provider_episode.get("plot")
        or ""
    )
    result["episode_released"] = (
        result.get("episode_released")
        or provider_episode.get("released")
        or ""
    )
    return result


async def _fetch_anime_tv(title, season, episode, encoded_string, year, quality) -> dict | None:
    try:
        result = await fetch_anime_metadata(title, season, episode, encoded_string, year, quality)
    except Exception as e:
        LOGGER.warning(f"[ANIME] metadata error for '{title}': {e}")
        return None
    if result is None:
        return None
    if not result.get("imdb_id") and result.get("tmdb_id"):
        result["imdb_id"] = await _tmdb_external_imdb_id("tv", result["tmdb_id"])
    if not result.get("imdb_id"):
        LOGGER.info(f"[ANIME] No imdb id for '{title}' -> falling back to TMDb/Cinemeta")
        return None
    result = await _enrich_anime_tv_artwork(result, int(season), int(episode))
    LOGGER.info(f"[ANIME] Matched '{result.get('title')}' [{result.get('imdb_id')}] S{season:02d}E{episode:02d}")
    return result


async def _fetch_anime_movie(title, encoded_string, year, quality) -> dict | None:
    try:
        result = await fetch_anime_movie_metadata(title, encoded_string, year, quality)
    except Exception as e:
        LOGGER.warning(f"[ANIME] movie metadata error for '{title}': {e}")
        return None
    if result is None:
        return None
    if not result.get("imdb_id") and result.get("tmdb_id"):
        result["imdb_id"] = await _tmdb_external_imdb_id("movie", result["tmdb_id"])
    if not result.get("imdb_id"):
        LOGGER.info(f"[ANIME] No imdb id for movie '{title}' -> falling back to TMDb/Cinemeta")
        return None
    LOGGER.info(f"[ANIME] Matched movie '{result.get('title')}' [{result.get('imdb_id')}]")
    return result


#----- ── TV & movie resolution ───────────────────────────────────────────────────
async def fetch_tv_metadata(
    title, season, episode, encoded_string, year=None, quality=None, default_id=None,
    *, absolute_episode: Optional[int] = None, episode_hint: Optional[str] = None,
) -> dict | None:
    imdb_id, tmdb_id, explicit_imdb_id, use_tmdb = _split_default_id(default_id)
    imdb_tv = None
    imdb_ep = None

    if not imdb_id and not tmdb_id:
        imdb_id = await safe_imdb_search(title, "tvSeries", year)
        use_tmdb = not bool(imdb_id)

    if imdb_id and not use_tmdb:
        try:
            imdb_tv = await _cached_imdb_detail(imdb_id, "tvSeries")
            if absolute_episode:
                mapped = _map_absolute_episode(imdb_tv, absolute_episode, episode_hint)
                if mapped:
                    season, episode = mapped
                    LOGGER.info("[AbsoluteEpisode] %s #%s -> S%02dE%02d", title, absolute_episode, season, episode)
            imdb_ep = await _cached_imdb_season(imdb_id, season, episode)
        except Exception as e:
            LOGGER.warning(f"IMDb TV fetch failed [{imdb_id}] -> {e}")
            imdb_tv = imdb_ep = None
            use_tmdb = True

    if imdb_tv and not imdb_ep and not explicit_imdb_id:
        LOGGER.info("Cinemeta series has no S%02dE%02d for '%s' -> TMDb", season, episode, title)
        imdb_tv = None
        use_tmdb = True

    if imdb_tv and not use_tmdb and not explicit_imdb_id:
        matched_title = imdb_tv.get("title", "")
        if not _cinemeta_title_compatible(title, matched_title):
            LOGGER.info("IMDb TV title mismatch for '%s': got '%s' -> TMDb", title, matched_title)
            imdb_tv = None
            use_tmdb = True

    if use_tmdb or not imdb_tv:
        LOGGER.info("No valid Cinemeta TV data for '%s' S%02dE%02d -> using TMDb", title, season, episode)
        if not tmdb_id:
            tmdb_search = await safe_tmdb_search(title, "tv", year)
            if not tmdb_search and year:
                tmdb_search = await safe_tmdb_search(title, "tv", None)
            if not tmdb_search:
                return None
            tmdb_id = tmdb_search.id
        tv = await _tmdb_details("tv", tmdb_id)
        if not tv:
            return None
        ep = await _tmdb_episode_details(tmdb_id, season, episode)
        return _build_tmdb_tv_payload(tv, ep, season, episode, quality, encoded_string)

    return _build_imdb_tv_payload(imdb_tv, imdb_ep or {}, imdb_id, title, season, episode, quality, encoded_string)

async def fetch_movie_metadata(title, encoded_string, year=None, quality=None, default_id=None) -> dict | None:
    imdb_id, tmdb_id, explicit_imdb_id, use_tmdb = _split_default_id(default_id)
    imdb_details = None

    if not imdb_id and not tmdb_id:
        imdb_id = await safe_imdb_search(title, "movie", year)
        use_tmdb = not bool(imdb_id)

    if imdb_id and not use_tmdb:
        try:
            imdb_details = await _cached_imdb_detail(imdb_id, "movie")
        except Exception as e:
            LOGGER.warning(f"IMDb movie fetch failed [{title}] -> {e}")
            imdb_details = None
            use_tmdb = True

    #----- Reject a wrong Cinemeta hit (skipped for user-supplied ids).
    if imdb_details and not use_tmdb and not explicit_imdb_id:
        sim = _title_similarity(title, imdb_details.get("title", ""))
        if sim < _CINEMETA_THRESHOLD:
            LOGGER.info(f"IMDb movie title mismatch for '{title}': got '{imdb_details.get('title', '')}' (sim={sim:.2f}) -> TMDb")
            imdb_details = None
            use_tmdb = True

    if use_tmdb or not imdb_details:
        LOGGER.info(f"No valid Cinemeta movie data for '{title}' (year={year}) -> using TMDb")
        if not tmdb_id:
            tmdb_result = await safe_tmdb_search(title, "movie", year) or (await safe_tmdb_search(title, "movie", None) if year else None)
            if not tmdb_result:
                LOGGER.info(f"No TMDb movie found for '{title}' (year={year})")
                return None
            tmdb_id = tmdb_result.id

        movie = await _tmdb_details("movie", tmdb_id)
        if not movie:
            LOGGER.info(f"TMDb movie details failed for id={tmdb_id} ('{title}')")
            return None
        return _build_tmdb_movie_payload(movie, quality, encoded_string)

    return _build_imdb_movie_payload(imdb_details, imdb_id, title, quality, encoded_string)


#----- ── Main entry point ────────────────────────────────────────────────────────
_METADATA_URL_RE = re.compile(r"(?i)\b(?:https?|ftp)://[^\s]+")
_METADATA_ONLY_ID_RE = re.compile(r"(?i)\btt\d{7,10}\b")


def _clean_metadata_candidate(value: object) -> str:
    """Return usable caption/filename text for metadata parsing.

    Telegram captions often include links, upload notes, or line breaks around
    the release name.  Remove only URL noise and normalize whitespace here;
    PTN still receives the original release wording, language, and tags.
    """
    raw_text = str(value or "")
    # Prefer the first supported filename in a multi-line Telegram caption.
    # This removes donation/channel text after `.mkv`, `.srt`, split ZIP
    # suffixes, etc., while preserving the complete release name itself.
    text = extract_supported_filename(raw_text) or raw_text
    text = _METADATA_URL_RE.sub(" ", text)
    text = re.sub(r"[\r\n\t]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" `\"'")
    if not text:
        return ""

    # A caption consisting only of an IMDb/default-ID marker has no searchable
    # title. Let the filename supply the title while metadata() still receives
    # the ID as a fallback signal when a real caption contains both values.
    meaningful = _METADATA_ONLY_ID_RE.sub("", text)
    meaningful = re.sub(r"(?i)\b(?:imdb|tmdb|default|media|id|sub)\b", "", meaningful)
    meaningful = re.sub(r"[^\w]+", "", meaningful, flags=re.UNICODE)
    return text if len(meaningful) >= 2 else ""


def metadata_source_candidates(caption: object, filename: object) -> list[tuple[str, str]]:
    """Return caption-first metadata candidates with a filename fallback.

    The returned order is intentionally strict: no filename parsing occurs
    until the caption candidate has failed provider resolution.  Duplicate text
    is removed so a caption identical to the filename is never queried twice.
    """
    caption_source = _clean_metadata_candidate(caption)
    filename_source = _clean_metadata_candidate(filename)
    candidates: list[tuple[str, str]] = []
    if caption_source:
        candidates.append(("caption", caption_source))
    if filename_source and filename_source.casefold() != caption_source.casefold():
        candidates.append(("filename", filename_source))
    return candidates


async def metadata_from_caption_or_filename(
    *, caption: object, filename: object, channel: int, msg_id,
    override_id: str | None = None, season_hint: int | None = None,
    split_info_override: SplitFileInfo | None = None,
) -> dict | None:
    candidates = metadata_source_candidates(caption, filename)
    resolved_override = override_id or extract_default_id(str(caption or ""))
    for source_kind, source in candidates:
        result = await metadata(
            str(filename or source), channel, msg_id,
            override_id=resolved_override, season_hint=season_hint,
            split_info_override=split_info_override,
            match_source=source, quality_source=str(filename or source),
        )
        if result is not None:
            result["metadata_source"] = source_kind
            result["source_caption"] = str(caption or "")
            result["source_filename"] = str(filename or "")
            LOGGER.info("Metadata resolved from %s for message %s", source_kind, msg_id)
            return result
        if source_kind == "caption":
            LOGGER.info("Caption metadata failed for message %s; trying filename", msg_id)
    return None


async def metadata(
    filename: str, channel: int, msg_id, override_id: str = None,
    season_hint: int = None, split_info_override: SplitFileInfo | None = None,
    *, match_source: str | None = None, quality_source: str | None = None,
) -> dict | None:
    split_info = split_info_override or detect_split_file(filename)
    parse_target = split_info.media_filename if split_info else filename
    parse_source = str(match_source or parse_target or "").strip()
    quality_source = str(quality_source or parse_target or parse_source).strip()

    if not split_info and _MULTIPART_RE.search(parse_source):
        LOGGER.info("Skipping %s: unsupported multipart naming", filename)
        return None

    try:
        parsed = parse_media_name(parse_source)
    except Exception as e:
        LOGGER.error(f"Parsing failed for {filename}: {e}\n{traceback.format_exc()}")
        return None

    combined = parse_combined_episodes(parse_source)
    excess = parsed.get("excess") or []
    if not combined and any("combined" in str(item).lower() for item in excess):
        LOGGER.info("Skipping %s: combined marker has no readable season", filename)
        return None

    title = parsed.get("title")
    season = parsed.get("season")
    episode = parsed.get("episode")
    year = parsed.get("year") or _release_year_from_source(parse_source)
    quality = parsed.get("quality") or _infer_quality_from_name(quality_source) or "HD"

    if isinstance(season, list) or isinstance(episode, list):
        LOGGER.warning("Invalid season/episode format for %s: %s", filename, parsed)
        return None

    special_title, special_episode = _special_episode_parts(parse_source)
    recovered_title, recovered_episode, recovered_episode_title = _release_episode_parts(parse_source, parsed)
    if recovered_episode is None and parsed.get("title"):
        recovered_title, recovered_episode, recovered_episode_title = _release_episode_parts(str(parsed.get("title") or ""), parsed)

    has_explicit_episode = _has_explicit_episode_marker(parse_source) or special_episode is not None
    source_year = _release_year_from_source(parse_source)

    if special_episode is not None:
        title = special_title or title
        season, episode = 0, special_episode
        recovered_episode = None
    elif source_year and not has_explicit_episode:
        season = episode = None
        recovered_episode = None
        title = _release_title_candidate(parse_source, title, year or source_year)
    elif (season is not None or episode is not None) and not has_explicit_episode and recovered_episode is None:
        LOGGER.info("Ignoring unverified parser episode for %s; treating as movie", parse_source)
        season = episode = None
        title = _release_title_candidate(parse_source, title, year)

    episode_title_hint = parsed.get("episodeName") or recovered_episode_title
    absolute_episode = None
    if season is None and recovered_episode is not None:
        title = recovered_title or title
        episode = recovered_episode
        season = season_hint if season_hint is not None else 1
        absolute_episode = recovered_episode
    elif season is None and episode is not None:
        season = season_hint if season_hint is not None else 1
        absolute_episode = int(episode)

    if combined:
        season, episode = combined["season"], combined["start"] or 1
    elif season is not None and episode is None:
        combined = {"season": season, "start": None, "end": None}
        episode = 1

    if season is not None and episode is None:
        LOGGER.warning("Missing episode in %s: %s", filename, parsed)
        return None
    if not title:
        LOGGER.info("No title parsed from %s (parsed=%s)", filename, parsed)
        return None

    default_id = _resolve_default_id(override_id, f"{parse_source} {filename}")
    try:
        encoded_string = await encode_string({"chat_id": channel, "msg_id": msg_id})
    except Exception:
        encoded_string = None

    anime_channel = _is_anime_channel(channel)
    try:
        if season is not None and episode is not None:
            LOGGER.info("Fetching TV metadata: %s S%02dE%02d (year=%s)", title, season, episode, year)
            result = None
            if not default_id and anime_channel:
                result = await _fetch_anime_tv(title, season, episode, encoded_string, year, quality)
            if result is None:
                result = await fetch_tv_metadata(
                    title, season, episode, encoded_string, year, quality, default_id,
                    absolute_episode=absolute_episode, episode_hint=episode_title_hint,
                )
            if result is not None and combined:
                _apply_combined_override(result, combined)
        else:
            LOGGER.info("Fetching Movie metadata: %s (year=%s)", title, year)
            result = None
            if not default_id and anime_channel:
                result = await _fetch_anime_movie(title, encoded_string, year, quality)
            if result is None:
                result = await fetch_movie_metadata(title, encoded_string, year, quality, default_id)

        if result is not None:
            if anime_channel:
                result["is_anime"] = True
            if split_info:
                result.update(split_metadata_fields(channel, quality, split_info))
            else:
                result.update({"group_key": None, "part_number": None, "split_kind": None, "media_filename": None})
        return result
    except Exception as e:
        LOGGER.error(f"Error while fetching metadata for {filename}: {e}\n{traceback.format_exc()}")
        return None

def _resolve_default_id(override_id, filename) -> str | None:
    for source in (override_id, getattr(Backend, "USE_DEFAULT_ID", None), filename):
        if not source:
            continue
        try:
            found = extract_default_id(source) or (override_id if source is override_id else None)
        except Exception:
            found = None
        if found:
            return found
    return None


def analyze_metadata_failure(filename: str) -> str:
    if _MULTIPART_RE.search(filename or ""):
        return "Looks like a multi-part video split (e.g. part1 / cd1) that can't be combined for streaming."

    split_info = parse_split_info(filename or "")
    parse_target = strip_part_suffix(filename) if split_info else (filename or "")

    try:
        parsed = parse_media_name(parse_target)
    except Exception:
        return "The file name / caption could not be parsed. Give it a clear name like 'Movie Name (2021) 1080p'."

    combined = parse_combined_episodes(parse_target)
    excess = parsed.get("excess")
    if not combined and excess and any("combined" in str(item).lower() for item in excess):
        return "The caption says 'combined' but no season number could be read from it (e.g. name it 'Show S02 Combined')."

    title = parsed.get("title")
    season = parsed.get("season")
    episode = parsed.get("episode")
    quality = parsed.get("quality")

    if not combined and (isinstance(season, list) or isinstance(episode, list)):
        return ("The name spans multiple seasons (e.g. S01-S03) that can't be filed as one entry. "
                "Upload one season per file. Combined episode packs within a single season are fine "
                "when named like 'Show S02 E01-E05' or 'Show S02 Combined'.")
    if not quality:
        return "No video quality/resolution was found. Add one to the caption (e.g. 480p, 720p, 1080p or 2160p)."
    if not title:
        return "No title could be detected. Rename or caption the file with a clear title."

    return ("Could not match this title on Cinemeta / TMDB. Fix the title/year in the caption, "
            "or add an IMDb link/id (tt...) or a TMDB link/id, then forward it again.")


#----- ── Candidate search (/set command UI) ──────────────────────────────────────
def _candidate_entry(source, title, year, imdb_id, tmdb_id, poster, backdrop, subtitle, media_type=None) -> dict:
    selected_id = imdb_id if (source == "imdb" and imdb_id) else (str(tmdb_id) if tmdb_id else (imdb_id or None))
    return {
        "source": source,
        "media_type": media_type,
        "title": title or "",
        "year": year or "",
        "imdb_id": imdb_id,
        "tmdb_id": tmdb_id,
        "selected_id": selected_id,
        "poster": poster,
        "backdrop": backdrop,
        "subtitle": subtitle,
    }


async def _resolve_id_candidate(default_id, media_type: str) -> dict | None:
    imdb_id, tmdb_id, _explicit_imdb, use_tmdb = _split_default_id(default_id)

    if imdb_id and not use_tmdb:
        imdb_type = "movie" if media_type == "movie" else "tvSeries"
        detail = None
        try:
            detail = await _cached_imdb_detail(imdb_id, imdb_type)
        except Exception as e:
            LOGGER.warning(f"IMDb id candidate resolve failed for '{imdb_id}': {e}")
        images = format_imdb_images(imdb_id)
        if detail and detail.get("title"):
            return _candidate_entry(
                "imdb", detail.get("title", ""), detail.get("releaseDetailed", {}).get("year", ""),
                imdb_id, detail.get("moviedb_id"), detail.get("poster") or images["poster"],
                detail.get("background") or images["backdrop"], "IMDb / Cinemeta", media_type,
            )
        return _candidate_entry("imdb", "", "", imdb_id, None, images["poster"], images["backdrop"], "IMDb / Cinemeta", media_type)

    if tmdb_id:
        details = await _tmdb_details(media_type, tmdb_id)
        if not details:
            return None
        r_title, r_year = _tmdb_title_year(details, media_type)
        imdb_ext = getattr(getattr(details, "external_ids", None), "imdb_id", None)
        return _candidate_entry(
            "tmdb", r_title, r_year or "", imdb_ext, tmdb_id,
            format_tmdb_image(getattr(details, "poster_path", None)),
            format_tmdb_image(getattr(details, "backdrop_path", None), "original"),
            "TMDb", media_type,
        )

    return None


async def _search_candidates(query: str, media_type: str, year: int | None = None, limit: int = 8) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []

    default_id = extract_default_id(query)
    if default_id:
        candidate = await _resolve_id_candidate(default_id, media_type)
        return [candidate] if candidate else []

    imdb_type = "movie" if media_type == "movie" else "tvSeries"
    results: list[dict] = []
    seen: set[tuple[str, str]] = set()

    try:
        imdb_hits = await search_title_multi(query=query, type=imdb_type, limit=limit)
        for hit in imdb_hits:
            hid = hit.get("id")
            if not hid or ("imdb", hid) in seen:
                continue
            seen.add(("imdb", hid))
            images = format_imdb_images(hid)
            results.append(_candidate_entry(
                "imdb", hit.get("title", ""), hit.get("year", ""),
                hid, None, hit.get("poster") or images["poster"], images["backdrop"],
                "IMDb / Cinemeta", media_type,
            ))
    except Exception as e:
        LOGGER.warning(f"IMDb {media_type} candidate search failed for '{query}': {e}")

    try:
        tmdb_results = await _tmdb_raw_search(query, media_type, year if media_type == "movie" else None)
        for item in (tmdb_results or [])[:limit]:
            tmdb_id = getattr(item, "id", None)
            if not tmdb_id or ("tmdb", str(tmdb_id)) in seen:
                continue
            seen.add(("tmdb", str(tmdb_id)))
            imdb_id = await _tmdb_external_imdb_id(media_type, tmdb_id)
            r_title, r_year = _tmdb_title_year(item, media_type)
            results.append(_candidate_entry(
                "tmdb", r_title, r_year or "", imdb_id, tmdb_id,
                format_tmdb_image(getattr(item, "poster_path", None)),
                format_tmdb_image(getattr(item, "backdrop_path", None), "original"),
                "TMDb", media_type,
            ))
    except Exception as e:
        LOGGER.warning(f"TMDb {media_type} candidate search failed for '{query}': {e}")

    return results[:limit]


async def search_movie_candidates(query: str, year: int | None = None, limit: int = 8) -> list[dict]:
    return await _search_candidates(query, "movie", year, limit)


async def search_tv_candidates(query: str, limit: int = 8) -> list[dict]:
    return await _search_candidates(query, "tv", None, limit)


async def search_any_candidates(query: str, year: int | None = None, limit: int = 8) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []

    default_id = extract_default_id(query)
    if default_id:
        out: list[dict] = []
        seen: set[tuple] = set()
        for mt in ("movie", "tv"):
            candidate = await _resolve_id_candidate(default_id, mt)
            if not candidate or not candidate.get("title"):
                continue
            key = (candidate.get("imdb_id"), str(candidate.get("tmdb_id")), mt)
            if key in seen:
                continue
            seen.add(key)
            out.append(candidate)
        return out

    results = await search_movie_candidates(query, year, limit)
    results += await search_tv_candidates(query, limit)
    return results


def build_id_link(imdb_id=None, tmdb_id=None, media_type: str = "movie") -> str | None:
    if imdb_id and str(imdb_id).startswith("tt"):
        return f"https://www.imdb.com/title/{imdb_id}/"
    if tmdb_id is not None and str(tmdb_id).lstrip("-").isdigit() and int(tmdb_id) > 0:
        path = "movie" if media_type == "movie" else "tv"
        return f"https://www.themoviedb.org/{path}/{tmdb_id}"
    return None


def caption_with_id(caption: str, metadata_info: dict) -> str | None:
    link = build_id_link(
        metadata_info.get("imdb_id"), metadata_info.get("tmdb_id"),
        metadata_info.get("media_type", "movie"),
    )
    if not link:
        return None
    base = (caption or "").strip()
    if extract_default_id(base):
        return None
    return f"{base}\n{link}" if base else link


#----- ── Manual /set helpers ─────────────────────────────────────────────────────
def _to_selection_payload(data: dict, media_type: str) -> dict:
    return {
        "tmdb_id": data.get("tmdb_id"),
        "imdb_id": data.get("imdb_id"),
        "title": data.get("title"),
        "release_year": data.get("year"),
        "rating": data.get("rate"),
        "description": data.get("description"),
        "poster": data.get("poster"),
        "backdrop": data.get("backdrop"),
        "logo": data.get("logo"),
        "genres": data.get("genres", []),
        "cast": data.get("cast", []),
        "runtime": data.get("runtime"),
        "media_type": media_type,
    }


async def fetch_selected_movie_metadata(selected_id: str) -> dict | None:
    selected_id = str(selected_id).strip()
    if not selected_id:
        return None
    data = await fetch_movie_metadata(
        title="manual-rescan", encoded_string=None, year=None, quality=None, default_id=selected_id
    )
    return _to_selection_payload(data, "movie") if data else None


async def fetch_selected_tv_metadata(selected_id: str) -> dict | None:
    selected_id = str(selected_id).strip()
    imdb_id, tmdb_id, _, use_tmdb = _split_default_id(selected_id)
    if not imdb_id and not tmdb_id:
        return None

    imdb_tv = None
    if imdb_id and not use_tmdb:
        try:
            imdb_tv = await get_detail(imdb_id=imdb_id, media_type="tvSeries")
        except Exception:
            imdb_tv = None
            use_tmdb = True

    if use_tmdb or not imdb_tv:
        if not tmdb_id and imdb_tv and imdb_tv.get("moviedb_id"):
            try:
                tmdb_id = int(imdb_tv["moviedb_id"])
            except Exception:
                tmdb_id = None
        if not tmdb_id:
            return None

        tv = await _tmdb_details("tv", tmdb_id)
        if not tv:
            return None
        first_air = getattr(tv, "first_air_date", None)
        runtime = _format_runtime(tv.episode_run_time[0] if getattr(tv, "episode_run_time", None) else None)
        return {
            "tmdb_id": tv.id,
            "imdb_id": getattr(getattr(tv, "external_ids", None), "imdb_id", None),
            "title": tv.name,
            "release_year": getattr(first_air, "year", 0) if first_air else 0,
            "rating": getattr(tv, "vote_average", 0) or 0,
            "description": tv.overview or "",
            "poster": format_tmdb_image(tv.poster_path),
            "backdrop": format_tmdb_image(tv.backdrop_path, "original"),
            "logo": get_tmdb_logo(getattr(tv, "images", None)),
            "genres": [g.name for g in (tv.genres or [])],
            "cast": _extract_cast(tv),
            "runtime": str(runtime),
            "media_type": "tv",
        }

    images = format_imdb_images(imdb_id)
    return {
        "tmdb_id": int(imdb_tv.get("moviedb_id")) if imdb_tv.get("moviedb_id") else None,
        "imdb_id": imdb_id,
        "title": imdb_tv.get("title", ""),
        "release_year": imdb_tv.get("releaseDetailed", {}).get("year", 0),
        "rating": imdb_tv.get("rating", {}).get("star", 0),
        "description": imdb_tv.get("plot", ""),
        "poster": images["poster"],
        "backdrop": images["backdrop"],
        "logo": images["logo"],
        "genres": imdb_tv.get("genre", []),
        "cast": imdb_tv.get("cast", []),
        "runtime": str(imdb_tv.get("runtime") or ""),
        "media_type": "tv",
    }
