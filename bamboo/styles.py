"""Reusable paragraph styles and independent chapter/page style contexts."""

from dataclasses import replace
from .model import TextStyle, SectionSpec, PRESETS

DEFAULT_STYLES = {
    s.key: s
    for s in (
        TextStyle("body", "正文"),
        TextStyle("heading", "题名", role="heading"),
        TextStyle("chapter-title", "篇章标题", bold=True, after=1, role="heading"),
        TextStyle("preface", "序言"),
        TextStyle("poetry", "诗文分行"),
        TextStyle("commentary", "课注", font_scale=0.75, role="commentary"),
        TextStyle("author", "作者署名", font_scale=0.75, align="end"),
        TextStyle("colophon", "题跋落款", font_scale=0.75, align="end", before=1),
        TextStyle("citation", "引文", font_scale=0.85, ink="#5b554a"),
        TextStyle(
            "cover-title",
            "题签书名",
            font_scale=1.8,
            ink="#b32624",
            align="center",
            role="heading",
        ),
        TextStyle(
            "cover-subtitle", "题签卷次", font_scale=0.8, ink="#b32624", align="center"
        ),
    )
}


def style_registry(book):
    return {**DEFAULT_STYLES, **{s.key: s for s in book.styles}}


def resolve_style(book, block):
    key = block.style or (
        "heading"
        if block.kind == "heading"
        else "commentary" if block.kind == "commentary" else "body"
    )
    return style_registry(book)[key]


def section_ranges(book):
    current = SectionSpec(
        profile=book.profile, title=book.title, volume=book.volume, author=book.author
    )
    start = 0
    result = []
    for i, block in enumerate(book.blocks):
        if block.section is not None:
            if i > start:
                result.append((start, i, current))
            spec = block.section
            current = replace(
                spec,
                profile=spec.profile or current.profile,
                title=current.title if spec.title is None else spec.title,
                volume=current.volume if spec.volume is None else spec.volume,
                author=current.author if spec.author is None else spec.author,
            )
            start = i
    result.append((start, len(book.blocks), current))
    return result


def context_at(book, index):
    return next(
        spec for start, end, spec in section_ranges(book) if start <= index < end
    )


def page_style_presets():
    red = PRESETS["woodblock"].updated(
        border_color="#c52c27",
        line_color="#e1b3ad",
        fish_tail_color="#c52c27",
        paper="#ffffff",
        rows=22,
        font_size=17,
        spine_rules=False,
    )
    return {
        "red-preface": ("朱栏序言", red),
        "poetry-page": ("诗文疏排", red.updated(rows=18, font_size=18)),
        "dense-classic": ("典籍密排", red.updated(rows=26, columns=12, font_size=14)),
        "ink-book": (
            "素墨古籍",
            PRESETS["woodblock"].updated(paper="#ffffff", fish_tail_style="outline"),
        ),
        "plain-page": ("无装饰书页", PRESETS["blank"]),
        "horizontal-page": ("横排书页", PRESETS["horizontal"]),
    }
