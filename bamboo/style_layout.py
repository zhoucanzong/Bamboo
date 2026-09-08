"""Title slips and editable text seals as geometry, not pre-rendered templates."""

from dataclasses import replace
import math
from .model import Glyph, Line, Polygon, Page, Layout, BambooError
from .styles import resolve_style


def rectangle(x, y, width, height, color, weight=0.7):
    return [
        Line(x, y, x + width, y, weight, color),
        Line(x + width, y, x + width, y + height, weight, color),
        Line(x + width, y + height, x, y + height, weight, color),
        Line(x, y + height, x, y, weight, color),
    ]


def place_seal(inline, p, x, y, width, height, block, span):
    from .layout import clusters

    chars = clusters(inline.text)
    n = math.ceil(math.sqrt(len(chars)))
    side = min(width * 0.88, height * 0.88, p.font_size * 1.8)
    left = x + (width - side) / 2
    top = y + (height - side) / 2
    inset = side * 0.1
    cell = (side - 2 * inset) / n
    lines = rectangle(left, top, side, side, p.accent, max(0.7, side * 0.035))
    polygons = []
    if inline.seal_style == "white":
        polygons.append(
            Polygon(
                (
                    (left + 1, top + 1),
                    (left + side - 1, top + 1),
                    (left + side - 1, top + side - 1),
                    (left + 1, top + side - 1),
                ),
                p.accent,
            )
        )
    glyphs = []
    for i, (offset, char) in enumerate(chars):
        col, row = divmod(i, n)
        glyphs.append(
            Glyph(
                char,
                left + inset + (n - col - 1) * cell,
                top + inset + row * cell,
                cell,
                cell,
                cell * 0.8,
                "seal",
                block,
                span,
                offset,
                "#ffffff" if inline.seal_style == "white" else p.accent,
            )
        )
    return glyphs, lines, polygons


def compose_cover(book, spec):
    from .layout import clusters

    p = book.profile
    width = min(spec.cover_width, p.width - 2 * p.margin_x)
    height = min(p.height * 0.68, p.body_height)
    left = (p.width - width) / 2
    top = (p.height - height) / 2
    runs = []
    for bi, block in enumerate(book.blocks):
        style = resolve_style(book, block)
        if block.kind == "pagebreak":
            continue
        if any(i.kind not in {"text", "emphasis", "label"} for i in block.inlines):
            raise BambooError("题签封面只支持标题文字；请把注释和印章放到正文篇章")
        chars = [
            (ii, off, c)
            for ii, i in enumerate(block.inlines)
            for off, c in clusters(i.text)
            if c not in "\n\r\t"
        ]
        size = min(p.font_size * style.font_scale, width * 0.65)
        runs.append((bi, block, style, chars, size))
    desired = sum(
        max(1, len(chars)) * size * 1.5 + size * 0.6 for _, _, _, chars, size in runs
    )
    factor = min(1, (height - 24) / max(1, desired))
    if any(size * factor < 4 for _, _, _, chars, size in runs if chars):
        raise BambooError("题签文字过多，无法在可读字号下排入")
    content_height = desired * factor
    y = top + (height - content_height) / 2
    glyphs = []
    starts = []
    for bi, block, style, chars, size in runs:
        actual = size * factor
        step = actual * 1.5
        starts.append(
            {
                "block": bi,
                "page": 0,
                "x": left + 6,
                "y": y,
                "width": width - 12,
                "height": step,
            }
        )
        for ii, off, c in chars:
            glyphs.append(
                Glyph(
                    c,
                    left + 6,
                    y,
                    width - 12,
                    step,
                    actual,
                    "cover",
                    bi,
                    ii,
                    off,
                    (
                        p.accent
                        if block.inlines[ii].kind == "emphasis"
                        else style.ink or p.ink
                    ),
                    bold=style.bold,
                )
            )
            y += step
        if not chars:
            y += step
        y += actual * 0.6
    color = p.border_color or next((s.ink for _, _, s, _, _ in runs if s.ink), p.accent)
    lines = (
        rectangle(left, top, width, height, color, 0.9)
        if spec.cover_border != "none"
        else []
    )
    if spec.cover_border == "double":
        lines += rectangle(left - 3, top - 3, width + 6, height + 6, color, 1.4)
    return Layout(
        book, (Page(1, tuple(glyphs), tuple(lines), ()),), block_starts=tuple(starts)
    )
