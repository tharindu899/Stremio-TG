import asyncio
import traceback
import httpx
import PTN
import re
from re import compile, IGNORECASE
from difflib import SequenceMatcher
from typing import Optional, List

from Backend.helper.imdb import get_detail, get_season, search_title, search_title_multi
from themoviedb import aioTMDb
from Backend.helper.settings_manager import SettingsManager
import Backend
from Backend.logger import LOGGER
from Backend.helper.encrypt import encode_string
from Backend.helper.split_files import detect_split_file, strip_part_suffix, split_metadata_fields

# ----------------- Configuration -----------------

DELAY = 0

_tmdb_client: aioTMDb | None = None
_tmdb_client_key: str | None = None


def get_tmdb_client() -> aioTMDb:
    global _tmdb_client, _tmdb_client_key

    current_key = SettingsManager.current().tmdb_api
    if _tmdb_client is None or _tmdb_client_key != current_key:
        _tmdb_client = aioTMDb(key=current_key, language="en-US", region="US")
        _tmdb_client_key = current_key

    return _tmdb_client


# Cache dictionaries (per run)
IMDB_CACHE: dict = {}
TMDB_SEARCH_CACHE: dict = {}
TMDB_DETAILS_CACHE: dict = {}
EPISODE_CACHE: dict = {}
ANILIST_TITLE_CACHE: dict[str, list[str]] = {}

# Concurrency semaphore for external API calls
API_SEMAPHORE = asyncio.Semaphore(12)
ANILIST_SEMAPHORE = asyncio.Semaphore(3)
_ANILIST_GRAPHQL_URL = "https://graphql.anilist.co"

# Minimum title-similarity score to accept a Cinemeta result
_CINEMETA_THRESHOLD = 0.60
# Minimum score to accept TMDb first-result (without year bonus it's stricter)
_TMDB_THRESHOLD = 0.55

# ----------------- Image helpers -----------------

def format_tmdb_image(path: str, size="w500") -> str:
    if not path:
        return ""
    return f"https://image.tmdb.org/t/p/{size}{path}"


def get_tmdb_logo(images) -> str:
    if not images:
        return ""
    logos = getattr(images, "logos", None)
    if not logos:
        return ""
    for logo in logos:
        iso_lang = getattr(logo, "iso_639_1", None)
        file_path = getattr(logo, "file_path", None)
        if iso_lang == "en" and file_path:
            return format_tmdb_image(file_path, "w300")
    for logo in logos:
        file_path = getattr(logo, "file_path", None)
        if file_path:
            return format_tmdb_image(file_path, "w300")
    return ""


def format_imdb_images(imdb_id: str) -> dict:
    if not imdb_id:
        return {"poster": "", "backdrop": "", "logo": ""}
    return {
        "poster": f"https://images.metahub.space/poster/small/{imdb_id}/img",
        "backdrop": f"https://images.metahub.space/background/medium/{imdb_id}/img",
        "logo": f"https://images.metahub.space/logo/medium/{imdb_id}/img",
    }


# ----------------- ID extraction -----------------

def extract_default_id(text: str) -> str | None:
    """
    Extract an IMDb (tt…) or TMDb (numeric) ID from arbitrary text.

    Handles:
    • Bare IMDb IDs:      tt1234567
    • IMDb URLs:          https://www.imdb.com/title/tt1234567/
    • TMDb movie URLs:    https://www.themoviedb.org/movie/12345
    • TMDb TV URLs:       https://www.themoviedb.org/tv/12345
    • Bare TMDb IDs are intentionally NOT extracted from plain numbers to
      avoid false matches; they must come via a URL or an explicit override.
    """
    if not text:
        return None

    # 1. Bare IMDb ID  (tt followed by 7–10 digits, word-bounded)
    bare_imdb = re.search(r'\b(tt\d{7,10})\b', text)
    if bare_imdb:
        return bare_imdb.group(1)

    # 2. IMDb URL
    imdb_url = re.search(r'/title/(tt\d+)', text)
    if imdb_url:
        return imdb_url.group(1)

    # 3. TMDb URL  (/movie/NNN or /tv/NNN)
    tmdb_url = re.search(r'/(?:movie|tv)/(\d+)', text)
    if tmdb_url:
        return tmdb_url.group(1)

    return None


# ----------------- Fuzzy-matching helpers -----------------

# Tokens that are too broad to safely identify a translated / romanized title
# by themselves.  They are ignored only by the conservative alternate-title
# fallback below; normal fuzzy matching still uses the full title.
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
    """Extract the first 4-digit year from strings like '2023', '2020–', '2019-2022'."""
    if not year_val:
        return 0
    m = re.search(r"(\d{4})", str(year_val))
    return int(m.group(1)) if m else 0


def _score_candidate(
    query_title: str,
    query_year: Optional[int],
    result_title: str,
    result_year: int,
) -> float:
    """Combined score for a single API candidate."""
    score = _title_similarity(query_title, result_title)

    if query_year and result_year:
        diff = abs(int(query_year) - result_year)
        if diff == 0:
            score = min(1.0, score + 0.20)   # exact year: strong boost
        elif diff == 1:
            score = min(1.0, score + 0.07)   # off by one: small boost
        elif diff <= 2:
            pass                              # neutral
        else:
            score = max(0.0, score - 0.10 * (diff - 2))  # growing penalty

    return score


def _build_query_variants(title: str, year: Optional[int] = None) -> List[str]:
    """Build safe, ordered provider-search variants for release filenames."""
    title = str(title or "").strip()
    if not title:
        return []

    variants: List[str] = [title]

    # Joined release aliases such as `ReZero` are common in filenames.  Keep
    # the original first, then offer a spaced form to providers.
    camel_spaced = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", title)
    camel_spaced = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", " ", camel_spaced)
    camel_spaced = re.sub(r"\s+", " ", camel_spaced).strip()
    if camel_spaced and camel_spaced.casefold() != title.casefold():
        variants.append(camel_spaced)

    # Title with year appended (often improves movie recall).
    if year:
        variants.append(f"{title} {year}")
        if camel_spaced and camel_spaced.casefold() != title.casefold():
            variants.append(f"{camel_spaced} {year}")

    # Punctuation-stripped versions (handles colons, hyphens, apostrophes).
    for source in (title, camel_spaced):
        stripped = re.sub(r"[^\w\s]", " ", source)
        stripped = re.sub(r"\s+", " ", stripped).strip()
        if stripped and stripped.casefold() != source.casefold():
            variants.append(stripped)
            if year:
                variants.append(f"{stripped} {year}")

    # Without leading article (The / A / An).
    no_article = re.sub(r"^\b(the|a|an)\b\s+", "", title, flags=IGNORECASE).strip()
    if no_article and no_article.casefold() != title.casefold():
        variants.append(no_article)

    # Deduplicate, preserve order, drop empty strings.
    seen: set[str] = set()
    result: List[str] = []
    for value in variants:
        key = value.casefold().strip()
        if key and key not in seen:
            seen.add(key)
            result.append(value.strip())
    return result


# ----------------- Anime title bridge -----------------

_ANILIST_TITLE_QUERY = """
query ($search: String!) {
  Page(page: 1, perPage: 5) {
    media(search: $search, type: ANIME) {
      id
      episodes
      startDate { year }
      title { romaji english native userPreferred }
    }
  }
}
"""


async def _anilist_title_variants(title: str, year: Optional[int] = None) -> list[str]:
    """Return high-confidence canonical anime title variants for a release name.

    This is a last-resort bridge for romaji / translated anime filenames.  It
    does not store any user data, needs no API key, and is called only after
    normal TV matching has already failed.  We accept the AniList result only
    when one of its own registered title forms exactly or nearly exactly matches
    the parsed filename title.
    """
    normalized = _normalize_title(title)
    cache_key = f"{normalized}::{year or 0}"
    if cache_key in ANILIST_TITLE_CACHE:
        return ANILIST_TITLE_CACHE[cache_key]

    meaningful = [token for token in _title_tokens(title) if token not in _ALIAS_STOPWORDS]
    if len(meaningful) < 2 or len("".join(meaningful)) < 5:
        ANILIST_TITLE_CACHE[cache_key] = []
        return []

    try:
        async with ANILIST_SEMAPHORE:
            async with httpx.AsyncClient(timeout=httpx.Timeout(7.0, connect=4.0)) as client:
                response = await client.post(
                    _ANILIST_GRAPHQL_URL,
                    json={"query": _ANILIST_TITLE_QUERY, "variables": {"search": title}},
                    headers={"Accept": "application/json"},
                )
                response.raise_for_status()
                payload = response.json()
    except Exception as exc:
        LOGGER.debug("AniList title bridge unavailable for '%s': %s", title, exc)
        ANILIST_TITLE_CACHE[cache_key] = []
        return []

    candidates = (
        payload.get("data", {})
        .get("Page", {})
        .get("media", [])
        if isinstance(payload, dict)
        else []
    )

    best_titles: list[str] = []
    best_score = 0.0
    for item in candidates or []:
        if not isinstance(item, dict):
            continue
        item_year = ((item.get("startDate") or {}).get("year"))
        if year and item_year and abs(int(year) - int(item_year)) > 3:
            continue
        title_map = item.get("title") or {}
        registered = [
            title_map.get("romaji"),
            title_map.get("english"),
            title_map.get("native"),
            title_map.get("userPreferred"),
        ]
        source_score = max(
            (_registered_alias_score(title, candidate) for candidate in registered if candidate),
            default=0.0,
        )
        if source_score < 0.90:
            continue
        if source_score > best_score:
            # Try the English distributor title first, then keep the other
            # valid catalogue spellings as fallback provider queries.
            ordered = [title_map.get("english"), title_map.get("romaji"), title_map.get("userPreferred")]
            clean: list[str] = []
            seen: set[str] = set()
            for candidate in ordered:
                if not isinstance(candidate, str):
                    continue
                candidate = candidate.strip()
                key = candidate.casefold()
                if candidate and key not in seen:
                    seen.add(key)
                    clean.append(candidate)
            best_titles = clean
            best_score = source_score

    ANILIST_TITLE_CACHE[cache_key] = best_titles
    return best_titles


# ----------------- Cached API wrappers -----------------

async def safe_imdb_search(title: str, type_: str, year: Optional[int] = None) -> str | None:
    """
    Search Cinemeta for *title* (+ optional *year*) with:
    • Multiple query variants (original, stripped, with-year, no-article)
    • Fuzzy title + year scoring across all returned results
    • Acceptance threshold so partial/wrong matches are rejected early
    • INFO log explaining what happened when no confident match is found
    """
    cache_key = f"imdb::{type_}::{title}::{year}"
    if cache_key in IMDB_CACHE:
        return IMDB_CACHE[cache_key]

    query_variants = _build_query_variants(title, year)

    best_id: str | None = None
    best_score: float = 0.0
    best_result_title: str = ""
    rejected_title: str = ""
    rejected_score: float = 0.0

    for query in query_variants:
        try:
            async with API_SEMAPHORE:
                results = await search_title_multi(query=query, type=type_, limit=8)

            for r in results:
                r_title = r.get("title", "")
                r_year = _year_from_str(r.get("year", ""))
                score = _score_candidate(title, year, r_title, r_year)

                # Keep character-level fuzzy scores from accepting unrelated
                # titles which only happen to share a suffix/plural spelling.
                if not _cinemeta_title_compatible(title, r_title):
                    if score > rejected_score:
                        rejected_score = score
                        rejected_title = r_title
                    continue

                if score > best_score:
                    best_score = score
                    best_id = r.get("id")
                    best_result_title = r_title

                # Early-exit: perfect / near-perfect match
                if best_score >= 0.92:
                    break

        except Exception as e:
            LOGGER.warning(f"Cinemeta search variant '{query}' [{type_}] failed: {e}")

        # Early-exit across variants too
        if best_score >= 0.92:
            break

    if best_score >= _CINEMETA_THRESHOLD and best_id:
        LOGGER.info(
            f"Cinemeta match: '{title}' (year={year}) → "
            f"'{best_result_title}' [{best_id}] (score={best_score:.2f})"
        )
        IMDB_CACHE[cache_key] = best_id
        return best_id

    # Log a clear, actionable INFO message so operators know why it fell back
    if best_id:
        LOGGER.info(
            f"Cinemeta low-confidence for '{title}' (year={year}, type={type_}) "
            f"| best candidate: '{best_result_title}' [{best_id}] score={best_score:.2f} "
            f"(threshold={_CINEMETA_THRESHOLD}) → falling back to TMDb"
        )
    elif rejected_title:
        LOGGER.info(
            f"Cinemeta rejected title mismatch for '{title}' (year={year}, type={type_}) "
            f"| candidate: '{rejected_title}' score={rejected_score:.2f} → falling back to TMDb"
        )
    else:
        LOGGER.info(
            f"Cinemeta returned no results for '{title}' (year={year}, type={type_}) "
            f"| tried variants: {query_variants} → falling back to TMDb"
        )

    IMDB_CACHE[cache_key] = None
    return None


async def safe_tmdb_search(
    title: str,
    type_: str,
    year: Optional[int] = None,
    *,
    allow_anime_bridge: bool = True,
):
    """Search TMDb with release-name variants and conservative alias fallback."""
    cache_key = f"tmdb_search::{type_}::{title}::{year}"
    if cache_key in TMDB_SEARCH_CACHE:
        return TMDB_SEARCH_CACHE[cache_key]

    try:
        all_results = []
        seen_ids: set[str] = set()
        query_variants = _build_query_variants(title, year) or [title]

        for query in query_variants:
            async with API_SEMAPHORE:
                if type_ == "movie":
                    results = (
                        await get_tmdb_client().search().movies(query=query, year=year)
                        if year
                        else await get_tmdb_client().search().movies(query=query)
                    )
                    # Year-constrained search sometimes returns nothing for
                    # new or limited releases.
                    if not results and year:
                        results = await get_tmdb_client().search().movies(query=query)
                else:
                    results = await get_tmdb_client().search().tv(query=query)

            for item in results or []:
                item_id = str(getattr(item, "id", "") or "")
                if not item_id or item_id in seen_ids:
                    continue
                seen_ids.add(item_id)
                all_results.append(item)

        best = _pick_best_tmdb_result(all_results, title, year, type_)

        # TMDb search already considers original, translated, and alternative
        # titles.  Search responses, however, expose only the preferred and
        # original display names.  For international releases that means a
        # correct result can be discarded simply because the romanized source
        # name is stored only in its alternative-title metadata.  Before
        # rejecting a low-score result, verify the first few TMDb candidates
        # against those registered aliases.  This is generic: no show/movie
        # title is hard-coded here.
        if best is None and all_results:
            best = await _pick_tmdb_registered_alias_result(
                all_results, title, year, type_
            )

        # Anime release names often use romaji while TMDb exposes an English
        # display label.  As a final TV-only bridge, resolve the title through
        # AniList's public anime catalogue and retry TMDb with the canonical
        # English/romaji variants.  It is reached only after all normal TMDb
        # matching and registered-alias checks have failed.
        if best is None and type_ == "tv" and allow_anime_bridge:
            for canonical_title in await _anilist_title_variants(title, year):
                if _normalize_title(canonical_title) == _normalize_title(title):
                    continue
                bridged = await safe_tmdb_search(
                    canonical_title,
                    "tv",
                    year,
                    allow_anime_bridge=False,
                )
                if bridged is not None:
                    LOGGER.info(
                        "AniList anime title bridge: '%s' → '%s' → TMDb '%s'",
                        title,
                        canonical_title,
                        getattr(bridged, "name", canonical_title),
                    )
                    best = bridged
                    break

        if best is None and all_results:
            top = all_results[0]
            top_title = getattr(top, "title" if type_ == "movie" else "name", "?")
            LOGGER.info(
                f"TMDb '{title}' (year={year}) top result '{top_title}' "
                f"did not meet threshold – no confident match"
            )

        TMDB_SEARCH_CACHE[cache_key] = best
        return best

    except Exception as e:
        LOGGER.error(f"TMDb search failed for '{title}' [{type_}]: {e}")
        TMDB_SEARCH_CACHE[cache_key] = None
        return None


def _pick_best_tmdb_result(results, query_title: str, query_year: Optional[int], type_: str):
    """Return the highest-confidence TMDb result without broad false matches."""
    if not results:
        return None

    best_item = None
    best_score = 0.0
    best_anchor_match = False

    for item in results:
        if type_ == "movie":
            release = getattr(item, "release_date", None)
            result_year = getattr(release, "year", 0) if release else 0
        else:
            first_air = getattr(item, "first_air_date", None)
            result_year = getattr(first_air, "year", 0) if first_air else 0

        candidate_titles = _result_titles(item, type_)
        if not candidate_titles:
            continue

        score = max(
            _score_candidate(query_title, query_year, candidate_title, result_year)
            for candidate_title in candidate_titles
        )
        anchor_match = (
            type_ == "tv"
            and any(_leading_alias_anchor(query_title, candidate_title) for candidate_title in candidate_titles)
        )

        # Do not lower global matching thresholds.  The anchor route is only
        # for long romanized TV titles whose first two meaningful words are an
        # exact registered-title prefix.
        if anchor_match:
            score = max(score, _TMDB_THRESHOLD + 0.01)

        if score > best_score:
            best_score = score
            best_item = item
            best_anchor_match = anchor_match

        if best_score >= 0.92:
            break

    if best_score >= _TMDB_THRESHOLD and best_item is not None:
        if best_anchor_match:
            title_value = getattr(best_item, "name", "") or getattr(best_item, "title", "") or "?"
            LOGGER.info(
                f"TMDb alternate-title anchor: '{query_title}' → '{title_value}' "
                f"(romanized title fallback)"
            )
        return best_item

    return None


def _value_from_mapping_or_object(value, *keys):
    """Read a field from either a TMDb model object or a raw API mapping."""
    if isinstance(value, dict):
        for key in keys:
            candidate = value.get(key)
            if candidate:
                return candidate
        return None
    for key in keys:
        candidate = getattr(value, key, None)
        if candidate:
            return candidate
    return None


def _as_list(value):
    """Normalize TMDb wrapper objects / dict payloads into a list."""
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    if isinstance(value, dict):
        for key in ("results", "titles", "translations"):
            nested = value.get(key)
            if isinstance(nested, (list, tuple, set)):
                return list(nested)
        return []
    for key in ("results", "titles", "translations"):
        nested = getattr(value, key, None)
        if isinstance(nested, (list, tuple, set)):
            return list(nested)
    return []


def _tmdb_registered_titles(details, type_: str) -> list[str]:
    """Collect preferred, original, translated and alternative TMDb titles.

    The package returns nested TMDb data as model objects on some versions and
    dictionaries on others, so this deliberately supports both shapes.
    """
    primary = "title" if type_ == "movie" else "name"
    original = "original_title" if type_ == "movie" else "original_name"
    result: list[str] = []
    seen: set[str] = set()

    def add(value):
        if not isinstance(value, str):
            return
        clean = value.strip()
        key = clean.casefold()
        if clean and key not in seen:
            seen.add(key)
            result.append(clean)

    add(_value_from_mapping_or_object(details, primary, original))
    add(_value_from_mapping_or_object(details, original, primary))

    alternatives = _value_from_mapping_or_object(details, "alternative_titles")
    for entry in _as_list(alternatives):
        add(_value_from_mapping_or_object(entry, "title", "name", "original_title", "original_name"))

    translations = _value_from_mapping_or_object(details, "translations")
    for translation in _as_list(translations):
        # TMDb translations place localized names inside a `data` object.
        payload = _value_from_mapping_or_object(translation, "data") or translation
        add(_value_from_mapping_or_object(payload, primary, original, "title", "name"))

    return result


def _registered_alias_score(query_title: str, alias: str) -> float:
    """Score only safe aliases; exact normalized aliases are always strongest."""
    query_norm = _normalize_title(query_title)
    alias_norm = _normalize_title(alias)
    if not query_norm or not alias_norm:
        return 0.0
    if query_norm == alias_norm:
        return 1.0

    # A registered alias can differ only by formatting/long dashes/spacing.
    # Keep fuzzy acceptance deliberately high so unrelated localized titles do
    # not become accidental matches.
    return _title_similarity(query_title, alias)


async def _pick_tmdb_registered_alias_result(results, query_title: str, query_year: Optional[int], type_: str):
    """Confirm a low-score TMDb candidate through its registered aliases.

    TMDb's search endpoint can find a romanized or translated title, but its
    compact result object may only return English/Japanese display labels.  We
    inspect the registered alias metadata for at most five candidates and only
    accept an exact or near-exact normalized title match.
    """
    meaningful = [token for token in _title_tokens(query_title) if token not in _ALIAS_STOPWORDS]
    if len(meaningful) < 2 or len("".join(meaningful)) < 5:
        return None

    best_item = None
    best_alias = ""
    best_score = 0.0

    for item in list(results or [])[:5]:
        item_id = getattr(item, "id", None)
        if not item_id:
            continue

        try:
            details = (
                await _tmdb_movie_details(item_id)
                if type_ == "movie"
                else await _tmdb_tv_details(item_id)
            )
        except Exception as exc:
            LOGGER.debug(
                "TMDb registered-title lookup failed for id=%s: %s", item_id, exc
            )
            continue

        if not details:
            continue

        if type_ == "movie":
            released = getattr(details, "release_date", None)
        else:
            released = getattr(details, "first_air_date", None)
        detail_year = getattr(released, "year", 0) if released else 0

        # An exact registered alias is enough when no release year was parsed.
        # If a year was parsed, reject a clearly unrelated candidate.
        year_gap = abs(int(query_year) - int(detail_year)) if query_year and detail_year else 0
        for alias in _tmdb_registered_titles(details, type_):
            score = _registered_alias_score(query_title, alias)
            exact = score >= 0.999
            if not exact and score < 0.93:
                continue
            if year_gap > 3 and not exact:
                continue
            if score > best_score:
                best_item = item
                best_alias = alias
                best_score = score

    if best_item is not None:
        display_title = getattr(
            best_item, "title" if type_ == "movie" else "name", "?"
        )
        LOGGER.info(
            "TMDb registered-title alias: '%s' → '%s' via '%s' (score=%.2f)",
            query_title,
            display_title,
            best_alias,
            best_score,
        )
        return best_item

    return None


async def _tmdb_movie_details(movie_id):
    if movie_id in TMDB_DETAILS_CACHE:
        return TMDB_DETAILS_CACHE[movie_id]
    try:
        async with API_SEMAPHORE:
            details = await get_tmdb_client().movie(movie_id).details(
                append_to_response="external_ids,credits,alternative_titles,translations"
            )
            images = await get_tmdb_client().movie(movie_id).images()
            details.images = images

        TMDB_DETAILS_CACHE[movie_id] = details
        return details
    except Exception as e:
        LOGGER.warning(f"TMDb movie details fetch failed for id={movie_id}: {e}")
        TMDB_DETAILS_CACHE[movie_id] = None
        return None


async def _tmdb_tv_details(tv_id):
    if tv_id in TMDB_DETAILS_CACHE:
        return TMDB_DETAILS_CACHE[tv_id]
    try:
        async with API_SEMAPHORE:
            details = await get_tmdb_client().tv(tv_id).details(
                append_to_response="external_ids,credits,alternative_titles,translations"
            )
            images = await get_tmdb_client().tv(tv_id).images()
            details.images = images
        TMDB_DETAILS_CACHE[tv_id] = details
        return details
    except Exception as e:
        LOGGER.warning(f"TMDb tv details fetch failed for id={tv_id}: {e}")
        TMDB_DETAILS_CACHE[tv_id] = None
        return None


async def _tmdb_episode_details(tv_id, season, episode):
    key = (tv_id, season, episode)
    if key in EPISODE_CACHE:
        return EPISODE_CACHE[key]
    try:
        async with API_SEMAPHORE:
            details = await get_tmdb_client().episode(tv_id, season, episode).details()
        EPISODE_CACHE[key] = details
        return details
    except Exception:
        EPISODE_CACHE[key] = None
        return None


# =============================================================================
# Release filename episode recovery
# =============================================================================

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
    raw = re.sub(r"(?i)\.(?:mkv|mp4|avi|ts|m4v|mov|wmv|webm|flv|mpeg|mpg)$", "", raw)
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


# =============================================================================
# Main entry-point
# =============================================================================

async def metadata(filename: str, channel: int, msg_id, override_id: str = None) -> dict | None:
    # Detect raw split videos and split ZIP archives before PTN parsing. PTN
    # only receives the clean original video filename, never `part001` or
    # `.zip.001`, so metadata matching stays identical to a normal upload.
    split_info = detect_split_file(filename)
    metadata_filename = split_info.media_filename if split_info else filename
    if split_info:
        LOGGER.info(
            "Split %s detected: %s → part %s (media: %s)",
            split_info.kind,
            filename,
            split_info.part_number,
            metadata_filename,
        )

    try:
        parsed = PTN.parse(metadata_filename)
    except Exception as e:
        LOGGER.error(f"PTN parsing failed for {filename}: {e}\n{traceback.format_exc()}")
        return None

    # Skip combined/invalid files.  Valid split parts are handled through
    # parse_split_info above and get merged into a virtual Stremio stream.
    if "excess" in parsed and any("combined" in item.lower() for item in parsed["excess"]):
        LOGGER.info(f"Skipping {filename}: contains 'combined'")
        return None

    part_number = split_info.part_number if split_info else None

    title = parsed.get("title")
    season = parsed.get("season")
    episode = parsed.get("episode")
    year = parsed.get("year")
    quality = parsed.get("resolution")

    if isinstance(season, list) or isinstance(episode, list):
        LOGGER.warning(f"Invalid season/episode format for {filename}: {parsed}")
        return None

    recovered_title, recovered_episode, recovered_episode_title = _release_episode_parts(metadata_filename, parsed)
    # PTN can strip a technical tail but leave ``Series - 1101`` inside its
    # title field. Retry that cleaned title so live uploads cannot fall through
    # to a movie lookup and trigger Replace Mode on unrelated episodes.
    if recovered_episode is None and parsed.get("title"):
        recovered_title, recovered_episode, recovered_episode_title = _release_episode_parts(
            str(parsed.get("title") or ""),
            parsed,
        )
    episode_title_hint = parsed.get("episodeName") or recovered_episode_title
    absolute_episode = None

    # Fansub/anime releases frequently use absolute numbering (e.g. `- 417`)
    # with no SxxExx marker.  Treat them as TV episodes and resolve the real
    # provider season/episode pair later, after the series metadata is known.
    if not season and recovered_episode is not None:
        title = recovered_title or title
        episode = recovered_episode
        season = 1
        absolute_episode = recovered_episode
    elif not season and episode:
        season = 1
        absolute_episode = int(episode)

    if season and not episode:
        LOGGER.warning(f"Missing episode in {filename}: {parsed}")
        return None
    if not quality:
        quality = "Unknown"
        LOGGER.info("No resolution in %s — indexing with Unknown quality.", filename)
    if not title:
        LOGGER.info(f"No title parsed from: {filename} (parsed={parsed})")
        return None

    # --- Resolve override / default ID ---
    default_id = None
    if override_id:
        try:
            default_id = extract_default_id(override_id) or override_id
        except Exception:
            pass

    if not default_id:
        try:
            default_id = extract_default_id(Backend.USE_DEFAULT_ID)
        except Exception:
            pass

    if not default_id:
        try:
            default_id = extract_default_id(filename)
        except Exception:
            pass

    data = {"chat_id": channel, "msg_id": msg_id}
    try:
        encoded_string = await encode_string(data)
    except Exception:
        encoded_string = None

    split_fields = split_metadata_fields(channel, quality, split_info) if split_info else {}

    try:
        if season and episode:
            LOGGER.info(f"Fetching TV metadata: {title} S{season:02d}E{episode:02d} (year={year})")
            result = await fetch_tv_metadata(
                title,
                season,
                episode,
                encoded_string,
                year,
                quality,
                default_id,
                absolute_episode=absolute_episode,
                episode_hint=episode_title_hint,
            )
        else:
            LOGGER.info(f"Fetching Movie metadata: {title} (year={year})")
            result = await fetch_movie_metadata(title, encoded_string, year, quality, default_id)
        if result is not None:
            if split_info:
                result.update(split_fields)
            else:
                result.update({
                    "group_key": None,
                    "part_number": None,
                    "split_kind": None,
                    "media_filename": None,
                })
        return result
    except Exception as e:
        LOGGER.error(f"Error while fetching metadata for {filename}: {e}\n{traceback.format_exc()}")
        return None


# =============================================================================
# TV metadata
# =============================================================================

async def fetch_tv_metadata(
    title,
    season,
    episode,
    encoded_string,
    year=None,
    quality=None,
    default_id=None,
    *,
    absolute_episode: Optional[int] = None,
    episode_hint: Optional[str] = None,
) -> dict | None:
    imdb_id = None
    tmdb_id = None
    imdb_tv = None
    imdb_ep = None
    use_tmdb = False
    explicit_imdb_id = False

    # ------------------------------------------------------------------
    # 1. Handle explicit default ID
    # ------------------------------------------------------------------
    if default_id:
        default_id = str(default_id)
        if default_id.startswith("tt"):
            imdb_id = default_id
            explicit_imdb_id = True
        elif default_id.isdigit():
            tmdb_id = int(default_id)
            use_tmdb = True

    # ------------------------------------------------------------------
    # 2. No ID → fuzzy Cinemeta search with query variants
    # ------------------------------------------------------------------
    if not imdb_id and not tmdb_id:
        imdb_id = await safe_imdb_search(title, "tvSeries", year)
        use_tmdb = not bool(imdb_id)

    # ------------------------------------------------------------------
    # 3. IMDb / Cinemeta detail fetch
    # ------------------------------------------------------------------
    if imdb_id and not use_tmdb:
        try:
            if imdb_id in IMDB_CACHE and isinstance(IMDB_CACHE.get(imdb_id), dict):
                imdb_tv = IMDB_CACHE[imdb_id]
            else:
                async with API_SEMAPHORE:
                    imdb_tv = await get_detail(imdb_id=imdb_id, media_type="tvSeries")
                IMDB_CACHE[imdb_id] = imdb_tv

            if absolute_episode:
                mapped_episode = _map_absolute_episode(imdb_tv, absolute_episode, episode_hint)
                if mapped_episode:
                    season, episode = mapped_episode
                    LOGGER.info(
                        "[AbsoluteEpisode] %s #%s → S%02dE%02d%s",
                        title,
                        absolute_episode,
                        season,
                        episode,
                        " (episode title matched)" if episode_hint else "",
                    )
                else:
                    LOGGER.info(
                        "[AbsoluteEpisode] %s #%s could not be mapped; using S%02dE%02d.",
                        title,
                        absolute_episode,
                        season,
                        episode,
                    )

            ep_key = f"{imdb_id}::{season}::{episode}"
            if ep_key in EPISODE_CACHE:
                imdb_ep = EPISODE_CACHE[ep_key]
            else:
                async with API_SEMAPHORE:
                    imdb_ep = await get_season(imdb_id=imdb_id, season_id=season, episode_id=episode)
                EPISODE_CACHE[ep_key] = imdb_ep

        except Exception as e:
            LOGGER.warning(f"IMDb TV fetch failed [{imdb_id}] → {e}")
            imdb_tv = None
            imdb_ep = None
            use_tmdb = True

    # A base-series result without the requested episode is not safe to use.
    # This happens with alternate edits and re-releases that share a title
    # but do not contain the requested season. Prefer TMDb's episode-aware
    # route instead of creating a wrong or empty episode record.
    if imdb_tv and not imdb_ep and not explicit_imdb_id:
        LOGGER.info(
            f"Cinemeta series '{imdb_tv.get('title', title)}' has no "
            f"S{season:02d}E{episode:02d} for '{title}' → using TMDb"
        )
        imdb_tv = None
        use_tmdb = True

    # ------------------------------------------------------------------
    # 4. Validate IMDb result against query title (guard against Cinemeta
    #    returning a stale wrong hit despite the fuzzy pre-filter).
    #    Skipped when the IMDb ID was supplied explicitly, since the user
    #    deliberately chose that exact ID.
    # ------------------------------------------------------------------
    if imdb_tv and not use_tmdb and not explicit_imdb_id:
        matched_title = imdb_tv.get("title", "")
        sim = _title_similarity(title, matched_title)
        if sim < _CINEMETA_THRESHOLD:
            LOGGER.info(
                f"IMDb detail title mismatch for '{title}': "
                f"got '{matched_title}' (sim={sim:.2f}) → switching to TMDb"
            )
            imdb_tv = None
            use_tmdb = True

    # ------------------------------------------------------------------
    # 5. Fallback: TMDb
    # ------------------------------------------------------------------
    must_use_tmdb = use_tmdb or not imdb_tv

    if must_use_tmdb:
        LOGGER.info(f"No valid Cinemeta TV data for '{title}' S{season:02d}E{episode:02d} → using TMDb")

        if not tmdb_id:
            # Try with year first, then without
            tmdb_search = await safe_tmdb_search(title, "tv", year)
            if not tmdb_search and year:
                tmdb_search = await safe_tmdb_search(title, "tv", None)

            if not tmdb_search:
                LOGGER.info(
                    f"No TMDb TV result for '{title}' S{season:02d}E{episode:02d} "
                    f"(year={year}) – metadata unavailable"
                )
                return None
            tmdb_id = tmdb_search.id

        tv = await _tmdb_tv_details(tmdb_id)
        if not tv:
            LOGGER.info(f"TMDb TV details failed for id={tmdb_id} ('{title}')")
            return None

        ep = await _tmdb_episode_details(tmdb_id, season, episode)

        credits = getattr(tv, "credits", None) or {}
        cast_arr = getattr(credits, "cast", []) or []
        cast = [
            getattr(c, "name", None) or getattr(c, "original_name", None)
            for c in cast_arr
        ]

        ep_runtime = getattr(ep, "runtime", None) if ep else None
        series_runtime = tv.episode_run_time[0] if getattr(tv, "episode_run_time", None) else None
        runtime_val = ep_runtime or series_runtime
        runtime = f"{runtime_val} min" if runtime_val else ""

        return {
            "tmdb_id": tv.id,
            "imdb_id": getattr(getattr(tv, "external_ids", None), "imdb_id", None),
            "title": tv.name,
            "year": getattr(tv.first_air_date, "year", 0) if getattr(tv, "first_air_date", None) else 0,
            "rate": getattr(tv, "vote_average", 0) or 0,
            "description": tv.overview or "",
            "poster": format_tmdb_image(tv.poster_path),
            "backdrop": format_tmdb_image(tv.backdrop_path, "original"),
            "logo": get_tmdb_logo(getattr(tv, "images", None)),
            "genres": [g.name for g in (tv.genres or [])],
            "media_type": "tv",
            "cast": cast,
            "runtime": str(runtime),
            "season_number": season,
            "episode_number": episode,
            "episode_title": getattr(ep, "name", f"S{season:02d}E{episode:02d}") if ep else f"S{season:02d}E{episode:02d}",
            "episode_backdrop": format_tmdb_image(getattr(ep, "still_path", None), "original") if ep else "",
            "episode_overview": getattr(ep, "overview", "") if ep else "",
            "episode_released": (
                ep.air_date.strftime("%Y-%m-%dT05:00:00.000Z")
                if getattr(ep, "air_date", None)
                else ""
            ),
            "quality": quality,
            "encoded_string": encoded_string,
        }

    # ------------------------------------------------------------------
    # 6. IMDb / Cinemeta path
    # ------------------------------------------------------------------
    imdb = imdb_tv or {}
    ep = imdb_ep or {}
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


# =============================================================================
# Movie metadata
# =============================================================================

async def fetch_movie_metadata(title, encoded_string, year=None, quality=None, default_id=None) -> dict | None:
    imdb_id = None
    tmdb_id = None
    imdb_details = None
    use_tmdb = False
    explicit_imdb_id = False

    # ------------------------------------------------------------------
    # 1. Explicit default ID
    # ------------------------------------------------------------------
    if default_id:
        default_id = str(default_id).strip()
        if default_id.startswith("tt"):
            imdb_id = default_id
            explicit_imdb_id = True
        elif default_id.isdigit():
            tmdb_id = int(default_id)
            use_tmdb = True

    # ------------------------------------------------------------------
    # 2. No ID → fuzzy Cinemeta search (tries year variants internally)
    # ------------------------------------------------------------------
    if not imdb_id and not tmdb_id:
        imdb_id = await safe_imdb_search(title, "movie", year)
        use_tmdb = not bool(imdb_id)

    # ------------------------------------------------------------------
    # 3. IMDb detail fetch
    # ------------------------------------------------------------------
    if imdb_id and not use_tmdb:
        try:
            if imdb_id in IMDB_CACHE and isinstance(IMDB_CACHE.get(imdb_id), dict):
                imdb_details = IMDB_CACHE[imdb_id]
            else:
                async with API_SEMAPHORE:
                    imdb_details = await get_detail(imdb_id=imdb_id, media_type="movie")
                IMDB_CACHE[imdb_id] = imdb_details

        except Exception as e:
            LOGGER.warning(f"IMDb movie fetch failed [{title}] → {e}")
            imdb_details = None
            use_tmdb = True

    # ------------------------------------------------------------------
    # 4. Validate IMDb result title against query
    #    (skipped when the IMDb ID was supplied explicitly — e.g. manual
    #     /set or web "Rescan Metadata" — since the user chose the exact ID)
    # ------------------------------------------------------------------
    if imdb_details and not use_tmdb and not explicit_imdb_id:
        matched_title = imdb_details.get("title", "")
        sim = _title_similarity(title, matched_title)
        if sim < _CINEMETA_THRESHOLD:
            LOGGER.info(
                f"IMDb detail title mismatch for '{title}': "
                f"got '{matched_title}' (sim={sim:.2f}) → switching to TMDb"
            )
            imdb_details = None
            use_tmdb = True

    # ------------------------------------------------------------------
    # 5. Fallback: TMDb
    # ------------------------------------------------------------------
    must_use_tmdb = use_tmdb or not imdb_details

    if must_use_tmdb:
        LOGGER.info(f"No valid Cinemeta movie data for '{title}' (year={year}) → using TMDb")

        if not tmdb_id:
            tmdb_result = await safe_tmdb_search(title, "movie", year)
            # Retry without year restriction for newer/unlisted titles
            if not tmdb_result and year:
                tmdb_result = await safe_tmdb_search(title, "movie", None)

            if not tmdb_result:
                LOGGER.info(
                    f"No TMDb movie found for '{title}' (year={year}) "
                    f"– metadata unavailable"
                )
                return None
            tmdb_id = tmdb_result.id

        movie = await _tmdb_movie_details(tmdb_id)
        if not movie:
            LOGGER.info(f"TMDb movie details failed for id={tmdb_id} ('{title}')")
            return None

        credits = getattr(movie, "credits", None) or {}
        cast_arr = getattr(credits, "cast", []) or []
        cast_names = [
            getattr(c, "name", None) or getattr(c, "original_name", None)
            for c in cast_arr
        ]

        runtime_val = getattr(movie, "runtime", None)
        runtime = f"{runtime_val} min" if runtime_val else ""

        return {
            "tmdb_id": movie.id,
            "imdb_id": getattr(movie.external_ids, "imdb_id", None),
            "title": movie.title,
            "year": getattr(movie.release_date, "year", 0) if getattr(movie, "release_date", None) else 0,
            "rate": getattr(movie, "vote_average", 0) or 0,
            "description": movie.overview or "",
            "poster": format_tmdb_image(movie.poster_path),
            "backdrop": format_tmdb_image(movie.backdrop_path, "original"),
            "logo": get_tmdb_logo(getattr(movie, "images", None)),
            "cast": cast_names,
            "runtime": str(runtime),
            "media_type": "movie",
            "genres": [g.name for g in (movie.genres or [])],
            "quality": quality,
            "encoded_string": encoded_string,
        }

    # ------------------------------------------------------------------
    # 6. IMDb / Cinemeta path
    # ------------------------------------------------------------------
    images = format_imdb_images(imdb_id)
    imdb = imdb_details or {}

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


# =============================================================================
# Candidate-search helpers (used by the /set command UI)
# =============================================================================

async def search_movie_candidates(query: str, year: int | None = None, limit: int = 8) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []

    results: list[dict] = []
    seen: set[tuple[str, str]] = set()

    try:
        imdb_result = await search_title(query=query, type="movie")
        if imdb_result and imdb_result.get("id"):
            key = ("imdb", imdb_result["id"])
            if key not in seen:
                seen.add(key)
                results.append({
                    "source": "imdb",
                    "title": imdb_result.get("title", ""),
                    "year": imdb_result.get("year", ""),
                    "imdb_id": imdb_result.get("id"),
                    "tmdb_id": imdb_result.get("moviedb_id"),
                    "poster": imdb_result.get("poster", ""),
                    "backdrop": "",
                    "subtitle": "IMDb / Cinemeta",
                })
    except Exception as e:
        LOGGER.warning(f"IMDb movie candidate search failed for '{query}': {e}")

    try:
        async with API_SEMAPHORE:
            tmdb_results = (
                await get_tmdb_client().search().movies(query=query, year=year)
                if year
                else await get_tmdb_client().search().movies(query=query)
            )

        for item in (tmdb_results or [])[:limit]:
            tmdb_id = getattr(item, "id", None)
            if not tmdb_id:
                continue

            imdb_id = None
            try:
                details = await _tmdb_movie_details(tmdb_id)
                ext = getattr(details, "external_ids", None) if details else None
                imdb_id = getattr(ext, "imdb_id", None) if ext else None
            except Exception:
                pass

            key = ("tmdb", str(tmdb_id))
            if key in seen:
                continue
            seen.add(key)

            release_date = getattr(item, "release_date", None)
            year_value = getattr(release_date, "year", None) if release_date else None

            results.append({
                "source": "tmdb",
                "title": getattr(item, "title", "") or "",
                "year": year_value or "",
                "imdb_id": imdb_id,
                "tmdb_id": tmdb_id,
                "poster": format_tmdb_image(getattr(item, "poster_path", None)),
                "backdrop": format_tmdb_image(getattr(item, "backdrop_path", None), "original"),
                "subtitle": "TMDb",
            })
    except Exception as e:
        LOGGER.warning(f"TMDb movie candidate search failed for '{query}': {e}")

    return results[:limit]


async def search_tv_candidates(query: str, limit: int = 8) -> list[dict]:
    query = (query or "").strip()
    if not query:
        return []

    results: list[dict] = []
    seen: set[tuple[str, str]] = set()

    try:
        imdb_result = await search_title(query=query, type="tvSeries")
        if imdb_result and imdb_result.get("id"):
            key = ("imdb", imdb_result["id"])
            if key not in seen:
                seen.add(key)
                results.append({
                    "source": "imdb",
                    "title": imdb_result.get("title", ""),
                    "year": imdb_result.get("year", ""),
                    "imdb_id": imdb_result.get("id"),
                    "tmdb_id": imdb_result.get("moviedb_id"),
                    "poster": imdb_result.get("poster", ""),
                    "backdrop": "",
                    "subtitle": "IMDb / Cinemeta",
                })
    except Exception as e:
        LOGGER.warning(f"IMDb TV candidate search failed for '{query}': {e}")

    try:
        async with API_SEMAPHORE:
            tmdb_results = await get_tmdb_client().search().tv(query=query)

        for item in (tmdb_results or [])[:limit]:
            tmdb_id = getattr(item, "id", None)
            if not tmdb_id:
                continue

            imdb_id = None
            try:
                details = await _tmdb_tv_details(tmdb_id)
                ext = getattr(details, "external_ids", None) if details else None
                imdb_id = getattr(ext, "imdb_id", None) if ext else None
            except Exception:
                pass

            key = ("tmdb", str(tmdb_id))
            if key in seen:
                continue
            seen.add(key)

            first_air_date = getattr(item, "first_air_date", None)
            year_value = getattr(first_air_date, "year", None) if first_air_date else None

            results.append({
                "source": "tmdb",
                "title": getattr(item, "name", "") or "",
                "year": year_value or "",
                "imdb_id": imdb_id,
                "tmdb_id": tmdb_id,
                "poster": format_tmdb_image(getattr(item, "poster_path", None)),
                "backdrop": format_tmdb_image(getattr(item, "backdrop_path", None), "original"),
                "subtitle": "TMDb",
            })
    except Exception as e:
        LOGGER.warning(f"TMDb TV candidate search failed for '{query}': {e}")

    return results[:limit]


# =============================================================================
# Manual /set command helpers
# =============================================================================

async def fetch_selected_movie_metadata(selected_id: str) -> dict | None:
    selected_id = str(selected_id).strip()
    if not selected_id:
        return None

    data = await fetch_movie_metadata(
        title="manual-rescan",
        encoded_string=None,
        year=None,
        quality=None,
        default_id=selected_id
    )
    if not data:
        return None

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
        "media_type": "movie",
    }


async def fetch_selected_tv_metadata(selected_id: str) -> dict | None:
    selected_id = str(selected_id).strip()
    if not selected_id:
        return None

    imdb_id = None
    tmdb_id = None
    imdb_tv = None
    use_tmdb = False

    if selected_id.startswith("tt"):
        imdb_id = selected_id
    elif selected_id.isdigit():
        tmdb_id = int(selected_id)
        use_tmdb = True
    else:
        return None

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

        tv = await _tmdb_tv_details(tmdb_id)
        if not tv:
            return None

        credits = getattr(tv, "credits", None) or {}
        cast_arr = getattr(credits, "cast", []) or []
        cast = [
            getattr(c, "name", None) or getattr(c, "original_name", None)
            for c in cast_arr
        ]

        runtime_val = tv.episode_run_time[0] if getattr(tv, "episode_run_time", None) else None
        runtime = f"{runtime_val} min" if runtime_val else ""

        return {
            "tmdb_id": tv.id,
            "imdb_id": getattr(getattr(tv, "external_ids", None), "imdb_id", None),
            "title": tv.name,
            "release_year": getattr(tv.first_air_date, "year", 0) if getattr(tv, "first_air_date", None) else 0,
            "rating": getattr(tv, "vote_average", 0) or 0,
            "description": tv.overview or "",
            "poster": format_tmdb_image(tv.poster_path),
            "backdrop": format_tmdb_image(tv.backdrop_path, "original"),
            "logo": get_tmdb_logo(getattr(tv, "images", None)),
            "genres": [g.name for g in (tv.genres or [])],
            "cast": cast,
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
