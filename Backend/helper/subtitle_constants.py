"""Shared subtitle formats, language names, and media type helpers."""
from __future__ import annotations

from pathlib import PurePath
from typing import Optional

SUBTITLE_MIME_TYPES = {
    ".srt": "application/x-subrip",
    ".vtt": "text/vtt; charset=utf-8",
    ".ass": "text/x-ssa; charset=utf-8",
    ".ssa": "text/x-ssa; charset=utf-8",
    ".sub": "text/plain; charset=utf-8",
    ".smi": "text/plain; charset=utf-8",
    ".sami": "text/plain; charset=utf-8",
}

# Fallback used only after filename/caption language detection cannot identify
# any supported language.  This keeps unlabelled subtitle uploads usable in the
# Sinhala-first library while preserving every explicit language label.
DEFAULT_SUBTITLE_LANGUAGE = "si"


SUBTITLE_MIME_PREFIXES = (
    "application/x-subrip",
    "application/x-srt",
    "text/vtt",
    "text/x-ssa",
    "application/ass",
    "application/ssa",
    "application/smil",
    "text/plain",
)

LANGUAGE_NAMES = {
    "ar": "Arabic",
    "bn": "Bengali",
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fa": "Persian",
    "fr": "French",
    "hi": "Hindi",
    "id": "Indonesian",
    "it": "Italian",
    "ja": "Japanese",
    "ko": "Korean",
    "kn": "Kannada",
    "ml": "Malayalam",
    "ms": "Malay",
    "pt": "Portuguese",
    "ru": "Russian",
    "si": "Sinhala",
    "ta": "Tamil",
    "te": "Telugu",
    "tr": "Turkish",
    "ur": "Urdu",
    "zh": "Chinese",
    "und": "Unknown",
}

LANGUAGE_ALIASES = {
    "ar": ("arabic", "العربية", "عربي"),
    "bn": ("bengali", "bangla", "বাংলা"),
    "de": ("german", "deutsch"),
    "en": ("english", "eng"),
    "es": ("spanish", "espanol", "español"),
    "fa": ("persian", "farsi"),
    "fr": ("french", "francais", "français"),
    "hi": ("hindi", "हिन्दी", "हिंदी"),
    "id": ("indonesian", "bahasa indonesia"),
    "it": ("italian", "italiano"),
    "ja": ("japanese", "jpn", "jap", "jp", "日本語"),
    "ko": ("korean", "kor", "한국어"),
    "kn": ("kannada", "ಕನ್ನಡ"),
    "ml": ("malayalam", "മലയാളം"),
    "ms": ("malay", "bahasa melayu"),
    "pt": ("portuguese", "português", "brazilian"),
    "ru": ("russian", "русский"),
    "si": ("sinhala", "sinhalese", "sinh", "සිංහල"),
    "ta": ("tamil", "தமிழ்"),
    "te": ("telugu", "తెలుగు"),
    "tr": ("turkish", "türkçe"),
    "ur": ("urdu", "اردو"),
    "zh": ("chinese", "mandarin", "中文"),
}


def extension_from_filename(filename: str) -> str:
    """Return the final lowercase filename extension without trusting captions."""
    return PurePath((filename or "").strip()).suffix.lower()


def is_subtitle_file(filename: str, mime_type: str = "") -> bool:
    extension = extension_from_filename(filename)
    if extension in SUBTITLE_MIME_TYPES:
        return True
    lowered_mime = (mime_type or "").lower()
    return any(lowered_mime.startswith(prefix) for prefix in SUBTITLE_MIME_PREFIXES)


def subtitle_mime_type(filename: str) -> Optional[str]:
    return SUBTITLE_MIME_TYPES.get(extension_from_filename(filename))


def language_name(code: str) -> str:
    return LANGUAGE_NAMES.get((code or "und").lower(), LANGUAGE_NAMES["und"])
