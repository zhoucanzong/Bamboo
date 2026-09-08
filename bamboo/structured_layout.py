"""Shared text/table geometry for editable specialist documents."""

from dataclasses import replace
from decimal import Decimal
import math
from .model import Glyph, Page, Layout, BambooError
from .style_layout import rectangle
from .structured import GiftLedger, money, money_upper


def fitted_text(
    value,
    x,
    y,
    width,
    height,
    size,
    color,
    vertical=False,
    record="",
    field="",
    minimum=7,
):
    from .layout import clusters

    chars = clusters(value)
    padding = 4
    if width <= padding * 2 or height <= padding * 2:
        raise BambooError("字格空间不足，请增加纸张或减少每页记录数")

    # Account for explicit line breaks while fitting complete, readable text.
    def split(fs):
        cap = max(1, int(((height if vertical else width) - padding * 2) / (fs * 1.1)))
        lines = [[]]
        for off, c in chars:
            if c == "\n":
                lines.append([])
                continue
            if len(lines[-1]) >= cap:
                lines.append([])
            lines[-1].append((off, c))
        return lines

    actual = size
    while actual >= minimum:
        lines = split(actual)
        if len(lines) * actual * 1.35 <= (width if vertical else height) - padding * 2:
            break
        actual -= 0.5
    else:
        raise BambooError(
            f'“{field or "文字"}”内容无法在可读字号下排入，请缩短内容、增加纸张或减少每页记录数'
        )
    glyphs = []
    for line, items in enumerate(lines):
        for i, (offset, char) in enumerate(items):
            gx = (
                x + width - padding - (line + 1) * actual * 1.35
                if vertical
                else x + padding + i * actual * 1.1
            )
            gy = (
                y + padding + i * actual * 1.1
                if vertical
                else y + padding + line * actual * 1.35
            )
            glyphs.append(
                Glyph(
                    char,
                    gx,
                    gy,
                    actual * 1.35 if vertical else actual * 1.1,
                    actual * 1.1 if vertical else actual * 1.35,
                    actual,
                    "structured",
                    -3,
                    offset=offset,
                    color=color,
                    object_id=record,
                    field=field,
                )
            )
    return glyphs, actual


def text_widget(value, x, y, w, h, size, color, vertical=False, record="", field=""):
    gs, actual = fitted_text(value, x, y, w, h, size, color, vertical, record, field)
    return gs, {
        "kind": "text",
        "text": value,
        "x": x,
        "y": y,
        "width": w,
        "height": h,
        "size": actual,
        "color": color,
        "vertical": vertical,
        "record": record,
        "field": field,
    }


def table_widget(rows, widths, heights, x, y, size, p, vertical=False):
    cells = []
    gs = []
    lines = []
    top = y
    for ri, (row, height) in enumerate(zip(rows, heights)):
        left = x
        for ci, (cell, width) in enumerate(zip(row, widths)):
            value = cell["text"]
            glyphs, actual = fitted_text(
                value,
                left,
                top,
                width,
                height,
                size,
                p.ink,
                vertical,
                cell.get("record", ""),
                cell.get("field", ""),
            )
            gs.extend(glyphs)
            if p.border != "none":
                lines.extend(rectangle(left, top, width, height, p.rule_color, 0.55))
            cells.append(
                {
                    **cell,
                    "row": ri,
                    "column": ci,
                    "x": left,
                    "y": top,
                    "width": width,
                    "height": height,
                    "size": actual,
                    "vertical": vertical,
                    "color": p.ink,
                }
            )
            left += width
        top += height
    return (
        gs,
        lines,
        {
            "kind": "table",
            "x": x,
            "y": y,
            "width": sum(widths),
            "height": sum(heights),
            "widths": widths,
            "heights": heights,
            "cells": cells,
            "rows": len(rows),
            "columns": len(widths),
        },
    )


def frame(book, number):
    p = book.profile
    glyphs = []
    widgets = []
    title, w = text_widget(
        book.title, p.margin_x, 12, p.width - 2 * p.margin_x, 28, 16, p.ink
    )
    glyphs.extend(title)
    widgets.append(w)
    subtitle = book.special.occasion
    if book.special.date:
        subtitle += (" · " if subtitle else "") + book.special.date
    sub, w = text_widget(
        subtitle, p.margin_x, 40, p.width - 2 * p.margin_x, 23, 10, p.ink
    )
    glyphs.extend(sub)
    widgets.append(w)
    return glyphs, widgets


def gift_layout(book):
    p = book.profile
    doc = book.special
    pages = []
    width = p.width - 2 * p.margin_x
    top = max(68, p.margin_top)
    bottom = p.height - max(62, p.margin_bottom)
    fields = [
        ("name", "姓名"),
        ("amount", "礼金（元）"),
        ("uppercase", "金额大写"),
        ("gift", "礼品"),
        ("date", "日期"),
        ("note", "备注"),
    ]
    total = sum((money(r.amount) for r in doc.records), Decimal(0))
    chunks = []
    cursor = 0
    while cursor < len(doc.records) or not chunks:
        count = min(doc.per_page, len(doc.records) - cursor)
        # Fit each group before accepting its page; reduce group size for long fields.
        while True:
            records = doc.records[cursor : cursor + count]
            logical = []
            for r in records:
                logical.append(
                    [
                        {
                            "text": (
                                money_upper(r.amount)
                                if key == "uppercase"
                                else getattr(r, key)
                            ),
                            "record": r.id,
                            "field": key,
                            "editable": key != "uppercase",
                        }
                        for key, _ in fields
                    ]
                )
            if not logical:
                logical = [
                    [{"text": "", "record": "", "field": key} for key, _ in fields]
                ]
            if p.vertical:
                rows = [
                    [row[i] for row in reversed(logical)]
                    + [{"text": label, "header": True}]
                    for i, (key, label) in enumerate(fields)
                ]
                widths = [width / (len(logical) + 1)] * (len(logical) + 1)
                weights = [0.15, 0.14, 0.23, 0.18, 0.12, 0.18]
                heights = [(bottom - top) * v for v in weights]
            else:
                rows = [
                    [{"text": label, "header": True} for _, label in fields]
                ] + logical
                widths = [width * v for v in [0.14, 0.12, 0.23, 0.17, 0.14, 0.20]]
                heights = [30] + [
                    (bottom - top - 30) / max(len(logical), doc.per_page)
                ] * len(logical)
                if count < doc.per_page:
                    heights = [30] + [(bottom - top - 30) / max(1, count)] * len(
                        logical
                    )
            try:
                g, l, table = table_widget(
                    rows,
                    widths,
                    heights,
                    p.margin_x,
                    top,
                    min(p.font_size, 16),
                    p,
                    p.vertical,
                )
            except BambooError:
                if count > 1:
                    count -= 1
                    continue
                raise
            break
        number = len(pages) + 1
        glyphs, widgets = frame(book, number)
        glyphs += g
        widgets.append(table)
        subtotal = sum((money(r.amount) for r in records), Decimal(0))
        footer = f"本页小计：{subtotal:.2f} 元　总计：{total:.2f} 元　记录：{len(doc.records)} 笔　　第 {number} 页"
        gs, w = text_widget(footer, p.margin_x, p.height - 54, width, 24, 10, p.ink)
        glyphs += gs
        widgets.append(w)
        gs, w = text_widget(
            "合计大写：" + money_upper(format(total, ".2f")),
            p.margin_x,
            p.height - 30,
            width,
            24,
            9,
            p.ink,
        )
        glyphs += gs
        widgets.append(w)
        pages.append(
            Page(
                number,
                tuple(glyphs),
                tuple(l),
                (),
                profile=p,
                folio=number,
                widgets=tuple(widgets),
            )
        )
        cursor += count
        if cursor >= len(doc.records):
            break
    return tuple(pages)


def compose_special(book):
    pages = gift_layout(book)
    for page in pages:
        for g in page.glyphs:
            if (
                min(g.x, g.y) < 0
                or g.x + g.width > page.profile.width + 0.01
                or g.y + g.height > page.profile.height + 0.01
            ):
                raise BambooError("专用文档文字越界")
    return Layout(
        book,
        pages,
        block_starts=(
            {
                "block": 0,
                "page": 0,
                "x": book.profile.margin_x,
                "y": book.profile.margin_top,
                "width": 20,
                "height": 20,
            },
        ),
    )
