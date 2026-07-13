"""Telegram media-caption normalization helpers.

Only filenames ending in a format supported by this project are selected.
Everything after the first supported extension is discarded, which keeps
channel advertisements and donation notes out of metadata parsing and display
captions.
"""
from __future__ import annotations

from html import escape
import re

_VIDEO_EXTENSIONS = "mkv|mp4|avi|ts|m4v|mov|wmv|webm|flv|mpeg|mpg"
_SUBTITLE_EXTENSIONS = "srt|vtt|ass|ssa|sub|smi|sami"

# Order matters: split-ZIP and split-video suffixes must win before a plain
# video extension is accepted.
_SUPPORTED_SUFFIX_RE = re.compile(
    rf"""(?ix)
    (?:
        \.(?:{_VIDEO_EXTENSIONS})\.zip\.\d{{1,5}}
        |\.(?:{_VIDEO_EXTENSIONS})\.z\d{{2,4}}
        |\.(?:{_VIDEO_EXTENSIONS})\.zip
        |\.zip\.\d{{1,5}}
        |\.(?:{_VIDEO_EXTENSIONS})(?:
            [._\- ]+(?:part|pt|cd|disc|disk)[._\- ]*\d{{1,5}}
            |\.\d{{1,5}}
        )?
        |\.(?:{_SUBTITLE_EXTENSIONS})
    )
    (?=$|[\s`*_~|<>\[\](){{}}:;,!?—–-])
    """
)

_LEADING_LABEL_RE = re.compile(
    r"""(?ix)^
    (?:
        [\s>*_`~|\-–—•·▶▷►🎬📁📄]+|
        (?:file(?:name)?|name|video|subtitle|media)\s*[:=\-]\s*
    )+
    """
)


def _clean_candidate_prefix(value: str) -> str:
    candidate = str(value or "").strip()
    candidate = _LEADING_LABEL_RE.sub("", candidate).strip()
    # Remove common Markdown wrappers without changing valid brackets/tags in
    # the filename itself, e.g. ``[Group] Show [1080p].mkv``.
    candidate = candidate.strip(" `*_~|")
    return candidate.strip()


def extract_supported_filename(value: object) -> str:
    """Return the first supported filename found in caption-like text.

    The match stops exactly at the supported extension/split suffix. Text on
    following lines or after that suffix is intentionally ignored.
    """
    raw = str(value or "").replace("\u200b", "").replace("\ufeff", "")
    if not raw.strip():
        return ""

    for original_line in raw.splitlines() or [raw]:
        line = original_line.strip()
        if not line:
            continue
        match = _SUPPORTED_SUFFIX_RE.search(line)
        if not match:
            continue
        candidate = _clean_candidate_prefix(line[: match.end()])
        if candidate:
            return candidate
    return ""


def preferred_caption_filename(caption: object, filename: object) -> str:
    """Choose the filename used for automatic caption formatting.

    A non-empty custom caption with no supported filename is left untouched.
    Telegram's real filename is used only when the upload has no caption, as
    requested by the automatic-caption workflow.
    """
    caption_text = str(caption or "")
    caption_filename = extract_supported_filename(caption_text)
    if caption_filename:
        return caption_filename
    if caption_text.strip():
        return ""
    return extract_supported_filename(filename) or str(filename or "").strip()


def bold_caption(filename: object) -> str:
    """Build a safe HTML caption with the complete filename in bold."""
    value = str(filename or "").strip()
    return f"<b>{escape(value, quote=False)}</b>" if value else ""
