"""Anchored secondary text regions, laid out after the primary story."""

from dataclasses import replace
import math

from .model import AnnotationBox, BambooError, Glyph


def overlaps(a, b):
    return (
        a[0] < b[2] - 0.01
        and a[2] > b[0] + 0.01
        and a[1] < b[3] - 0.01
        and a[3] > b[1] + 0.01
    )


def add_annotations(layout):
    from .layout import clusters

    p = layout.book.profile
    pages = []
    anchors = {
        (g.block, g.inline, g.offset): (pi, g)
        for pi, page in enumerate(layout.pages)
        for g in page.glyphs
        if g.block >= 0
    }
    requests = []
    for bi, block in enumerate(layout.book.blocks):
        for ii, inline in enumerate(block.inlines):
            if inline.kind == "ruby":
                requests.append(
                    (
                        f"ruby-{bi}-{ii}",
                        "ruby",
                        bi,
                        ii,
                        0,
                        inline.annotation,
                        1,
                        len(inline.annotation),
                    )
                )
    for i, n in enumerate(layout.book.annotations):
        requests.append(
            (
                f"annotation-{i}",
                n.placement,
                n.block,
                n.inline,
                n.offset,
                n.text,
                n.columns,
                n.extent,
            )
        )
    added = {i: [] for i in range(len(layout.pages))}
    boxes = {i: [] for i in range(len(layout.pages))}
    for note_id, kind, bi, ii, offset, text, columns, extent in requests:
        if (bi, ii, offset) not in anchors:
            raise BambooError(f"批注 {note_id} 的锚点被隐藏或不在字素起点")
        pi, anchor = anchors[(bi, ii, offset)]
        size = p.font_size * 0.5
        step = size * 1.2
        count = len(clusters(text))
        if kind == "ruby":
            base = [
                g for g in layout.pages[pi].glyphs if (g.block, g.inline) == (bi, ii)
            ]
            extent = count
            available = len(base) * p.cell_advance
            if count * step > available:
                size = min(size, available / count / 1.2)
                step = size * 1.2
            if size < 4:
                raise BambooError("短旁注太密，请缩短注释或增加锚定正文")
        width, height = (
            (size * columns, extent * step)
            if p.vertical
            else (extent * step, size * columns)
        )
        if kind == "top":
            x = anchor.x + anchor.width / 2 - width / 2
            y = p.margin_top - height - 8
        elif p.vertical:
            x = anchor.x + anchor.width / 2 + anchor.size / 2 + 2
            y = anchor.y
        else:
            x = anchor.x
            y = anchor.y + anchor.height / 2 - anchor.size / 2 - height - 2
        # Deterministic local avoidance. Never shrink or clip an overflowing box.
        for existing in boxes[pi]:
            if overlaps(
                (x, y, x + width, y + height),
                (
                    existing.x,
                    existing.y,
                    existing.x + existing.width,
                    existing.y + existing.height,
                ),
            ):
                if kind == "top":
                    x = existing.x - width - 4
                elif p.vertical:
                    y = existing.y + existing.height + 4
                else:
                    x = existing.x + existing.width + 4
        if min(x, y) < 4 or x + width > p.width - 4 or y + height > p.height - 4:
            raise BambooError(f"批注 {note_id} 区域越界，请增加留白或调整注释范围")
        rect = (x, y, x + width, y + height)
        for g in layout.pages[pi].glyphs:
            if g.block < 0:
                continue
            ink = (
                g.x + (g.width - g.size) / 2,
                g.y + (g.height - g.size) / 2,
                g.x + (g.width + g.size) / 2,
                g.y + (g.height + g.size) / 2,
            )
            if overlaps(rect, ink):
                raise BambooError(
                    f"批注 {note_id} 与正文冲突，请加大行栏间距或缩小注释区域"
                )
        box = AnnotationBox(
            note_id, kind, bi, ii, offset, x, y, width, height, size, text
        )
        boxes[pi].append(box)
        for j, (off, char) in enumerate(clusters(text)):
            lane, cell = divmod(j, extent)
            gx, gy = (
                (x + (columns - lane - 1) * size, y + cell * step)
                if p.vertical
                else (x + cell * step, y + lane * size)
            )
            added[pi].append(
                Glyph(
                    char,
                    gx,
                    gy,
                    size if p.vertical else step,
                    step if p.vertical else size,
                    size,
                    "annotation",
                    -2,
                    ii,
                    off,
                    p.accent,
                    annotation_id=note_id,
                )
            )
    for i, page in enumerate(layout.pages):
        pages.append(
            replace(
                page, glyphs=page.glyphs + tuple(added[i]), annotations=tuple(boxes[i])
            )
        )
    return replace(layout, pages=tuple(pages))
