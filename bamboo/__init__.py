"""Bamboo's public, document-first typesetting API."""

from .engine import BuildResult, render
from .layout import compose
from .model import (
    Annotation,
    BambooError,
    Block,
    Book,
    Inline,
    Layout,
    PRESETS,
    Profile,
)
from .parser import from_dict, load, parse
from .editor import EditorSession, Position, Selection, RevisionConflict

__version__ = "0.4.0"
__all__ = [
    "Annotation",
    "BambooError",
    "Block",
    "Book",
    "Inline",
    "Layout",
    "Profile",
    "PRESETS",
    "BuildResult",
    "compose",
    "from_dict",
    "load",
    "parse",
    "render",
    "EditorSession",
    "Position",
    "Selection",
    "RevisionConflict",
]
