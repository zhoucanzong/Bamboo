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
            if cell.get("skip"):
                left += width
                continue
            value = cell["text"]
            width = sum(widths[ci : ci + cell.get("colspan", 1)])
            cell_height = sum(heights[ri : ri + cell.get("rowspan", 1)])
            cell_vertical = cell.get("vertical", vertical)
            glyphs, actual = fitted_text(
                value,
                left,
                top,
                width,
                cell_height,
                cell.get("size", size),
                p.ink,
                cell_vertical,
                cell.get("record", ""),
                cell.get("field", ""),
            )
            gs.extend(glyphs)
            if p.border != "none":
                lines.extend(
                    rectangle(left, top, width, cell_height, p.rule_color, 0.55)
                )
            cells.append(
                {
                    **cell,
                    "row": ri,
                    "column": ci,
                    "x": left,
                    "y": top,
                    "width": width,
                    "height": cell_height,
                    "size": actual,
                    "vertical": cell_vertical,
                    "color": p.ink,
                }
            )
            left += widths[ci]
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
        ("amount", "金额（元）"),
        ("uppercase", "金额大写"),
        ("gift", "物品"),
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
                    p.font_size,
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
    pages = {
        "genealogy": family_layout,
        "gift": gift_layout,
        "gongche": gongche_layout,
    }[book.special.kind](book)
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


def family_layout(book):
    from .structured import family_generations
    from .model import Line

    p = book.profile
    doc = book.special
    levels = family_generations(doc.records)
    ordered = sorted(enumerate(doc.records), key=lambda r: (levels[r[1].id], r[0]))
    people = [r for _, r in ordered]
    groups = [
        people[i : i + doc.per_page] for i in range(0, len(people), doc.per_page)
    ] or [[]]
    page_of = {r.id: i + 1 for i, group in enumerate(groups) for r in group}
    pages = []
    edges = []
    spouses = set()
    for r in doc.records:
        edges.extend((parent, r.id, "parent") for parent in r.parents)
        spouses.update(tuple(sorted((r.id, s))) for s in r.spouses)
    edges.extend((a, b, "spouse") for a, b in sorted(spouses))
    for pi, group in enumerate(groups):
        glyphs, widgets = frame(book, pi + 1)
        lines = []
        nodes = []
        positions = {}
        width = p.width - 2 * p.margin_x
        height = p.height - max(p.margin_top, 76) - 60
        top = max(p.margin_top, 76)
        used = sorted({levels[r.id] for r in group})
        bygen = {g: [r for r in group if levels[r.id] == g] for g in used}
        for gi, gen in enumerate(used):
            for ri, r in enumerate(bygen[gen]):
                if p.vertical:
                    band = width / len(used)
                    space = height / len(bygen[gen])
                    w = min(150, band * 0.62)
                    h = min(100, space * 0.76)
                    x = p.width - p.margin_x - (gi + 0.5) * band - w / 2
                    y = top + (ri + 0.5) * space - h / 2
                else:
                    band = height / len(used)
                    space = width / len(bygen[gen])
                    w = min(160, space * 0.76)
                    h = min(90, band * 0.60)
                    x = p.margin_x + (ri + 0.5) * space - w / 2
                    y = top + (gi + 0.5) * band - h / 2
                refs = []
                for label, targets in [
                    ("父母", r.parents),
                    (
                        "配偶",
                        [
                            s
                            for a, b, k in edges
                            if k == "spouse" and r.id in (a, b)
                            for s in [b if a == r.id else a]
                        ],
                    ),
                    ("子女", [b for a, b, k in edges if k == "parent" and a == r.id]),
                ]:
                    other = sorted(
                        {page_of[t] for t in targets if page_of[t] != pi + 1}
                    )
                    if other:
                        ranges = []
                        start = previous = other[0]
                        for n in other[1:] + [None]:
                            if n is not None and n == previous + 1:
                                previous = n
                                continue
                            ranges.append(
                                str(start)
                                if start == previous
                                else f"{start}—{previous}"
                            )
                            start = previous = n
                        refs.append(label + "见第" + ",".join(ranges) + "页")
                value = (
                    r.name + f"\n第{gen}世" + (("\n" + "；".join(refs)) if refs else "")
                )
                gs, node = text_widget(
                    value, x, y, w, h, 12, p.ink, p.vertical, r.id, "name"
                )
                glyphs += gs
                node["name"] = r.name
                node["kind"] = "node"
                nodes.append(node)
                positions[r.id] = node
                lines += rectangle(x, y, w, h, p.rule_color, 0.8)
        for a, b, kind in edges:
            if a not in positions or b not in positions:
                continue
            src, dst = positions[a], positions[b]
            color = p.accent if kind == "spouse" else p.ink
            if kind == "spouse":
                if p.vertical:
                    start = (src["x"] + src["width"], src["y"] + src["height"] / 2)
                    end = (dst["x"] + dst["width"], dst["y"] + dst["height"] / 2)
                    side = max(start[0], end[0]) + 10
                    path = [start, (side, start[1]), (side, end[1]), end]
                else:
                    start = (src["x"] + src["width"] / 2, src["y"])
                    end = (dst["x"] + dst["width"] / 2, dst["y"])
                    side = min(start[1], end[1]) - 10
                    path = [start, (start[0], side), (end[0], side), end]
                lines.extend(Line(*u, *v, 0.65, color) for u, v in zip(path, path[1:]))
                continue
            if p.vertical:
                start = (src["x"], src["y"] + src["height"] / 2)
                end = (dst["x"] + dst["width"], dst["y"] + dst["height"] / 2)
                mid = (start[0] + end[0]) / 2
                path = [start, (mid, start[1]), (mid, end[1]), end]
            else:
                start = (src["x"] + src["width"] / 2, src["y"] + src["height"])
                end = (dst["x"] + dst["width"] / 2, dst["y"])
                mid = (start[1] + end[1]) / 2
                path = [start, (start[0], mid), (end[0], mid), end]
            lines.extend(Line(*u, *v, 0.65, color) for u, v in zip(path, path[1:]))
        if not group:
            gs, node = text_widget(
                "点击纸面添加人物", p.margin_x, top, width, 40, 14, p.ink
            )
            glyphs += gs
            nodes.append(node)
        widgets.append(
            {
                "kind": "graph",
                "nodes": nodes,
                "lines": [
                    {
                        "x1": l.x1,
                        "y1": l.y1,
                        "x2": l.x2,
                        "y2": l.y2,
                        "color": l.color,
                        "width": l.width,
                    }
                    for l in lines[4 * len(positions) :]
                ],
                "height": height,
                "y": top,
            }
        )
        gs, w = text_widget(
            f"黑线：亲子　朱线：配偶　人物传记从第{len(groups)+1}页起　　第{pi+1}页",
            p.margin_x,
            p.height - 42,
            width,
            26,
            10,
            p.ink,
        )
        glyphs += gs
        widgets.append(w)
        pages.append(
            Page(
                pi + 1,
                tuple(glyphs),
                tuple(lines),
                (),
                profile=p,
                folio=pi + 1,
                widgets=tuple(widgets),
            )
        )
    byid = {r.id: r for r in doc.records}
    index = {r.id: i + 1 for i, r in enumerate(doc.records)}

    def relative(values):
        return "；".join(f"{index[i]} {byid[i].name}" for i in values)

    for person in doc.records:
        number = len(pages) + 1
        glyphs, widgets = frame(book, number)
        all_spouses = [
            b if a == person.id else a for a, b in spouses if person.id in (a, b)
        ]
        values = [
            ("name", "姓名", person.name),
            ("parents", "父母", relative(person.parents)),
            ("spouses", "配偶", relative(sorted(all_spouses, key=lambda i: index[i]))),
            ("birth", "生年", person.birth),
            ("death", "卒年", person.death),
            ("biography", "传记", person.biography),
        ]
        top = max(68, p.margin_top)
        height = p.height - top - 55
        rows = [
            [
                {"text": label, "header": True},
                {"text": value, "record": person.id, "field": key},
            ]
            for key, label, value in values
        ]
        if p.vertical:
            rows = [
                [
                    {"text": label, "header": True}
                    for key, label, value in reversed(values)
                ],
                [
                    {"text": value, "record": person.id, "field": key}
                    for key, label, value in reversed(values)
                ],
            ]
            widths = [
                (p.width - 2 * p.margin_x) * v for v in [0.5, 0.1, 0.1, 0.1, 0.1, 0.1]
            ]
            heights = [38, height - 38]
        else:
            widths = [
                (p.width - 2 * p.margin_x) * 0.14,
                (p.width - 2 * p.margin_x) * 0.86,
            ]
            heights = [32] * 5 + [height - 160]
        gs, lines, table = table_widget(
            rows, widths, heights, p.margin_x, top, p.font_size, p, p.vertical
        )
        glyphs += gs
        widgets.append(table)
        gs, w = text_widget(
            f"人物序号 {index[person.id]}　　第{levels[person.id]}世　　世系图见第{page_of[person.id]}页　　第{number}页",
            p.margin_x,
            p.height - 42,
            p.width - 2 * p.margin_x,
            26,
            10,
            p.ink,
        )
        glyphs += gs
        widgets.append(w)
        pages.append(
            Page(
                number,
                tuple(glyphs),
                tuple(lines),
                (),
                profile=p,
                folio=number,
                widgets=tuple(widgets),
            )
        )
    return tuple(pages)


def score_table(notes, p, x, y, width, height):
    fields = [
        ("lyric", "唱词"),
        ("symbol", "谱字"),
        ("beat", "板眼"),
        ("register", "音区"),
    ]
    if p.vertical:
        widths = [width * v for v in [0.45, 0.25, 0.15, 0.15]]
        heights = [26, 26] + [(height - 52) / len(notes)] * len(notes)
        rows = [
            [
                {
                    "text": notes[0].phrase,
                    "colspan": 4,
                    "vertical": False,
                    "record": notes[0].id,
                    "field": "phrase",
                },
                *({"skip": True} for _ in range(3)),
            ],
            [
                {"text": label, "header": True, "vertical": False}
                for key, label in fields
            ],
        ]
        covered = 0
        for i, note in enumerate(notes):
            rows.append(
                [
                    {
                        "text": getattr(note, key),
                        "record": note.id,
                        "field": key,
                        "size": (
                            min(p.font_size * 1.5, 24)
                            if key == "symbol"
                            else p.font_size
                        ),
                        **(
                            {"rowspan": note.lyric_span}
                            if key == "lyric" and note.lyric_span > 1
                            else {}
                        ),
                        **({"skip": True} if key == "lyric" and i < covered else {}),
                    }
                    for key, label in fields
                ]
            )
            if note.lyric_span > 1:
                covered = i + note.lyric_span
    else:
        fields = [
            ("register", "音区"),
            ("beat", "板眼"),
            ("symbol", "谱字"),
            ("lyric", "唱词"),
        ]
        widths = [42] + [(width - 42) / len(notes)] * len(notes)
        heights = [
            24,
            (height - 24) * 0.16,
            (height - 24) * 0.2,
            (height - 24) * 0.29,
            (height - 24) * 0.35,
        ]
        rows = [
            [
                {
                    "text": notes[0].phrase,
                    "colspan": len(widths),
                    "record": notes[0].id,
                    "field": "phrase",
                },
                *({"skip": True} for _ in notes),
            ]
        ]
        for key, label in fields:
            row = [{"text": label, "header": True}]
            covered = 0
            for i, note in enumerate(notes):
                row.append(
                    {
                        "text": getattr(note, key),
                        "record": note.id,
                        "field": key,
                        "size": (
                            min(p.font_size * 1.5, 24)
                            if key == "symbol"
                            else p.font_size
                        ),
                        **(
                            {"colspan": note.lyric_span}
                            if key == "lyric" and note.lyric_span > 1
                            else {}
                        ),
                        **({"skip": True} if key == "lyric" and i < covered else {}),
                    }
                )
                if note.lyric_span > 1:
                    covered = i + note.lyric_span
            rows.append(row)
    return table_widget(rows, widths, heights, x, y, 12, p, p.vertical)


def gongche_layout(book):
    p = book.profile
    doc = book.special
    width = p.width - 2 * p.margin_x
    top = max(70, p.margin_top)
    height = p.height - top - 54
    count = doc.systems_per_page
    gap = 12
    group_width = (width - gap * (count - 1)) / count if p.vertical else width
    group_height = height if p.vertical else (height - gap * (count - 1)) / count
    atoms = []
    i = 0
    while i < len(doc.records):
        span = doc.records[i].lyric_span
        atoms.append(list(doc.records[i : i + span]))
        i += span
    groups = []
    cursor = 0
    while cursor < len(atoms):
        end = cursor
        size = 0
        while (
            end < len(atoms)
            and atoms[end][0].phrase == atoms[cursor][0].phrase
            and size + len(atoms[end]) <= doc.per_page
        ):
            size += len(atoms[end])
            end += 1
        while True:
            notes = [r for atom in atoms[cursor:end] for r in atom]
            try:
                score_table(notes, p, 0, 0, group_width, group_height)
            except BambooError:
                if end > cursor + 1:
                    end -= 1
                    continue
                raise
            break
        groups.append(notes)
        cursor = end
    pages = []
    for start in range(0, max(1, len(groups)), count):
        page_groups = groups[start : start + count]
        number = len(pages) + 1
        glyphs, widgets = frame(book, number)
        lines = []
        tables = []
        for i, notes in enumerate(page_groups):
            x = (
                p.margin_x + (count - i - 1) * (group_width + gap)
                if p.vertical
                else p.margin_x
            )
            y = top if p.vertical else top + i * (group_height + gap)
            gs, ls, table = score_table(notes, p, x, y, group_width, group_height)
            glyphs += gs
            lines += ls
            tables.append(table)
        if not tables:
            gs, w = text_widget(
                "点击纸面录入谱字、板眼与唱词", p.margin_x, top, width, 40, 14, p.ink
            )
            glyphs += gs
            widgets.append(w)
        else:
            widgets.append(
                {
                    "kind": "score",
                    "tables": tables,
                    "width": width,
                    "height": height,
                    "vertical": p.vertical,
                }
            )
        gs, w = text_widget(
            f"工尺谱　谱字与唱词对应，板眼以原谱为准　　第{number}页",
            p.margin_x,
            p.height - 40,
            width,
            26,
            10,
            p.ink,
        )
        glyphs += gs
        widgets.append(w)
        pages.append(
            Page(
                number,
                tuple(glyphs),
                tuple(lines),
                (),
                profile=p,
                folio=number,
                widgets=tuple(widgets),
            )
        )
    return tuple(pages)
