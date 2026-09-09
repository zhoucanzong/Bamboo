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
    TextStyle,
    SectionSpec,
)
from .parser import from_dict, load, parse
from .editor import EditorSession, Position, Selection, RevisionConflict

from .structured import (
    GiftRecord,
    GiftLedger,
    FamilyPerson,
    Genealogy,
    GongcheNote,
    GongcheScore,
)

__version__ = "0.7.0"
__all__ = [
    "GiftRecord",
    "GiftLedger",
    "FamilyPerson",
    "Genealogy",
    "GongcheNote",
    "GongcheScore",
    "Annotation",
    "BambooError",
    "Block",
    "Book",
    "Inline",
    "Layout",
    "Profile",
    "TextStyle",
    "SectionSpec",
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
