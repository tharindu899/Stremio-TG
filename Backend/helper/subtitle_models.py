"""Typed, serialisable values used by the subtitle indexing pipeline."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class SubtitleIdentity:
    source_filename: str
    source_caption: str
    extension: str
    language_code: str
    language_name: str
    imdb_id: Optional[str] = None
    tmdb_id: Optional[int] = None
    title: str = ""
    normalized_title: str = ""
    release_year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None
    match_hint: str = "filename"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
