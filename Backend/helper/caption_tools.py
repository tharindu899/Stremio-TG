"""Telegram media-caption normalization helpers.

Only filenames ending in a format supported by this project are selected.
Everything after the first supported extension is discarded, which keeps
channel advertisements and donation notes out of metadata parsing and display
captions.
"""
from __future__ import annotations

from html import escape
import re

_VIDEO_EXTENSIONS = "mkv|mp4|avi|ts|m4v|mov|wmv|webm|flv|m2ts|mpeg|mpg"
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
    (?=$|[^A-Za-z0-9])
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

    Rules:
    * Caption contains the real Telegram filename plus extra text: keep exactly
      that filename, regardless of extension.
    * Caption contains another supported media/subtitle filename: preserve that
      caption filename and discard everything after its extension.
    * Caption is genuine custom text with no filename: leave it untouched.
    * Upload has no caption: add the real Telegram filename automatically.
    """
    caption_text = str(caption or "").replace("\u200b", "").replace("\ufeff", "")
    real_filename = str(filename or "").strip()

    if caption_text.strip():
        # The real Telegram filename is the strongest and safest boundary. This
        # also supports uncommon extensions without accidentally truncating a
        # normal custom caption.
        if real_filename:
            for original_line in caption_text.splitlines() or [caption_text]:
                line = _clean_candidate_prefix(original_line)
                if line.startswith(real_filename):
                    return real_filename

        caption_filename = extract_supported_filename(caption_text)
        if caption_filename:
            return caption_filename

        # A custom caption that does not contain a filename must not be changed.
        return ""

    return real_filename


def bold_caption(filename: object) -> str:
    """Build a safe HTML caption with the complete filename in bold."""
    value = str(filename or "").strip()
    return f"<b>{escape(value, quote=False)}</b>" if value else ""
