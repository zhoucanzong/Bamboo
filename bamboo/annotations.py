"""Anchored annotations, with optional flow through free interlinear lanes."""

from dataclasses import replace
import math
from .model import AnnotationBox, BambooError, Glyph, Page


def overlaps(a, b):
    return (
        a[0] < b[2] - 0.01
        and a[2] > b[0] + 0.01
        and a[1] < b[3] - 0.01
        and a[3] > b[1] + 0.01
    )


def ink(g):
    return (
        g.x + (g.width - g.size) / 2,
        g.y + (g.height - g.size) / 2,
        g.x + (g.width + g.size) / 2,
        g.y + (g.height + g.size) / 2,
    )


def rect(box):
    return (box.x, box.y, box.x + box.width, box.y + box.height)


def lanes(p, size, columns):
    result = []
    for col in range(p.columns * p.panels):
        panel, inner = divmod(col, p.columns)
        if p.vertical:
            right = (
                p.width - p.margin_x
                if p.panels == 1 or panel == 0
                else p.margin_x + p.panel_width
            )
            x = right - (inner + 1) * p.line_advance
            result.append(
                (
                    x + p.line_advance / 2 + p.font_size / 2 + 2,
                    p.margin_top,
                    size * columns,
                    p.body_height,
                    x,
                )
            )
        else:
            start = p.margin_x + (
                p.spine if p.panels == 1 else panel * (p.panel_width + p.spine)
            )
            y = p.margin_top + inner * p.line_advance
            result.append(
                (
                    start,
                    y + p.line_advance / 2 - p.font_size / 2 - 2 - size * columns,
                    p.panel_width,
                    size * columns,
                    y,
                )
            )
    return result


def free_intervals(lane, p, obstacles, start):
    x, y, w, h, _ = lane
    low, high = (y, y + h) if p.vertical else (x, x + w)
    low = max(low, start)
    intervals = [(low, high)] if low < high else []
    for a, b, c, d in obstacles:
        if p.vertical:
            if x >= c or x + w <= a:
                continue
            cut = (b - 2, d + 2)
        else:
            if y >= d or y + h <= b:
                continue
            cut = (a - 2, c + 2)
        new = []
        for lo, hi in intervals:
            if cut[1] <= lo or cut[0] >= hi:
                new.append((lo, hi))
                continue
            if cut[0] > lo:
                new.append((lo, min(hi, cut[0])))
            if cut[1] < hi:
                new.append((max(lo, cut[1]), hi))
        intervals = new
    return intervals


def add_annotations(layout, first_folio=1):
    from .layout import clusters, _frame

    p = layout.book.profile
    pages = list(layout.pages)
    anchors = {
        (g.block, g.inline, g.offset): (pi, g)
        for pi, page in enumerate(pages)
        for g in page.glyphs
        if g.block >= 0
    }
    requests = []
    for bi, block in enumerate(layout.book.blocks):
        for ii, inline in enumerate(block.inlines):
            if inline.kind == "ruby":
                requests.append(
                    dict(
                        id=f"ruby-{bi}-{ii}",
                        kind="ruby",
                        bi=bi,
                        ii=ii,
                        offset=0,
                        text=inline.annotation,
                        columns=1,
                        extent=len(clusters(inline.annotation)),
                        flow=False,
                        scale=0.5,
                        color=p.accent,
                    )
                )
    for i, n in enumerate(layout.book.annotations):
        requests.append(
            dict(
                id=f"annotation-{i}",
                kind=n.placement,
                bi=n.block,
                ii=n.inline,
                offset=n.offset,
                text=n.text,
                columns=n.columns,
                extent=n.extent,
                flow=n.flow,
                scale=n.font_scale,
                color=n.color or p.accent,
            )
        )
    added = {i: [] for i in range(len(pages))}
    boxes = {i: [] for i in range(len(pages))}
    warnings = list(layout.warnings)

    def emit(
        q, pi, x, y, size, cols, extent, chars, text_offset=0, part=0, anchor=None
    ):
        width, height = (
            (size * cols, extent * size * 1.2)
            if p.vertical
            else (extent * size * 1.2, size * cols)
        )
        source = anchor or anchors[(q["bi"], q["ii"], q["offset"])][1]
        bi, ii, offset = (
            (source.block, source.inline, source.offset)
            if source is not False
            else (-1, 0, 0)
        )
        value = "".join(c for _, c in chars)
        if q["flow"]:
            base, remainder = divmod(len(chars), cols)
            counts = (
                [base + int(i >= cols - remainder) for i in range(cols)]
                if base
                else [int(i < remainder) for i in range(cols)]
            )
        else:
            counts = [min(extent, max(0, len(chars) - i * extent)) for i in range(cols)]
        boundaries = []
        total = 0
        for count in counts[:-1]:
            total += count
            if 0 < total < len(chars):
                boundaries.append(chars[total][0] - text_offset)
        box = AnnotationBox(
            q["id"],
            q["kind"],
            bi,
            ii,
            offset,
            x,
            y,
            width,
            height,
            size,
            value,
            text_offset=text_offset,
            part=part,
            flow=q["flow"],
            color=q["color"],
            source_block=q["bi"],
            source_inline=q["ii"],
            source_offset=q["offset"],
            text_breaks=tuple(boundaries) if q["flow"] else (),
        )
        boxes[pi].append(box)
        for j, (off, char) in enumerate(chars):
            lane = 0
            cell = j
            while lane < len(counts) - 1 and cell >= counts[lane]:
                cell -= counts[lane]
                lane += 1
            gx, gy = (
                (x + (cols - lane - 1) * size, y + cell * size * 1.2)
                if p.vertical
                else (x + cell * size * 1.2, y + lane * size)
            )
            added[pi].append(
                Glyph(
                    char,
                    gx,
                    gy,
                    size if p.vertical else size * 1.2,
                    size * 1.2 if p.vertical else size,
                    size,
                    "annotation",
                    -2,
                    ii,
                    off,
                    q["color"],
                    annotation_id=q["id"],
                )
            )
        return box

    # Fixed annotations and short ruby are obstacles for the flowing story.
    for q in [q for q in requests if not q["flow"]]:
        key = q["bi"], q["ii"], q["offset"]
        if key not in anchors:
            raise BambooError(f"批注 {q['id']} 的锚点被隐藏或不在字素起点")
        pi, anchor = anchors[key]
        size = p.font_size * q["scale"]
        chars = clusters(q["text"])
        extent = q["extent"]
        if q["kind"] == "ruby":
            available = sum(
                g.width if not p.vertical else g.height
                for g in pages[pi].glyphs
                if (g.block, g.inline) == (q["bi"], q["ii"])
            )
            size = min(size, available / max(1, len(chars)) / 1.2)
        if size < 4:
            raise BambooError("批注字号过小，请增加正文或批注字号")
        width, height = (
            (size * q["columns"], extent * size * 1.2)
            if p.vertical
            else (extent * size * 1.2, size * q["columns"])
        )
        if q["kind"] == "top":
            x = anchor.x + anchor.width / 2 - width / 2
            y = p.margin_top - height - 8
        elif p.vertical:
            x = anchor.x + anchor.width / 2 + anchor.size / 2 + 2
            y = anchor.y
        else:
            x = anchor.x
            y = anchor.y + anchor.height / 2 - anchor.size / 2 - height - 2
        for _ in range(len(boxes[pi]) + 1):
            conflict = next(
                (
                    b
                    for b in boxes[pi]
                    if overlaps((x, y, x + width, y + height), rect(b))
                ),
                None,
            )
            if conflict is None:
                break
            if q["kind"] == "top":
                x = conflict.x - width - 4
            elif p.vertical:
                y = conflict.y + conflict.height + 4
            else:
                x = conflict.x + conflict.width + 4
        if min(x, y) < 4 or x + width > p.width - 4 or y + height > p.height - 4:
            raise BambooError(f"批注 {q['id']} 区域越界，请增加留白或调整注释范围")
        if any(
            overlaps((x, y, x + width, y + height), ink(g))
            for g in pages[pi].glyphs
            if g.block >= 0
        ):
            raise BambooError(
                f"批注 {q['id']} 与正文冲突，请加大行栏间距或缩小注释区域"
            )
        emit(q, pi, x, y, size, q["columns"], extent, chars)

    # Short comments retain their nearby positions; longer comments use the gaps
    # and then subsequent reading lanes/pages without dropping text.
    flowing = sorted(
        (q for q in requests if q["flow"]),
        key=lambda q: (len(clusters(q["text"])), q["bi"], q["ii"], q["offset"]),
    )
    original_count = len(pages)
    for q in flowing:
        key = q["bi"], q["ii"], q["offset"]
        if key not in anchors:
            raise BambooError(f"批注 {q['id']} 的锚点被隐藏或不在字素起点")
        start_page, anchor = anchors[key]
        size = p.font_size * q["scale"]
        step = size * 1.2
        if size < 4:
            raise BambooError("批注字号过小，请增加正文或批注字号")
        candidates = lanes(p, size, q["columns"])
        first_lane = min(
            range(len(candidates)),
            key=lambda i: abs(
                candidates[i][4] - (anchor.x if p.vertical else anchor.y)
            ),
        )
        chars = clusters(q["text"])
        cursor = 0
        part = 0
        pi = start_page
        first_fragment = True
        while cursor < len(chars):
            if pi >= len(pages):
                if pi >= original_count + 1000:
                    raise BambooError("批注续排页数过多，请调整批注或版式")
                gs, ls, ps = _frame(layout.book, first_folio + pi)
                pages.append(Page(pi + 1, tuple(gs), tuple(ls), tuple(ps)))
                added[pi] = []
                boxes[pi] = []
            progress = cursor
            if q["kind"] == "top":
                # A top note stays in the upper margin. Multiple columns are
                # balanced to use the available height before moving left.
                h = p.margin_top - 20
                w = size * q["columns"]
                top_lanes = [
                    (x, 8, w, h, x)
                    for x in [
                        anchor.x + anchor.width / 2 - w / 2 - i * (w + 4)
                        for i in range(max(1, int(p.width / (w + 4))))
                    ]
                    if x >= 4 and x + w <= p.width - 4
                ]
                if not p.vertical:
                    h = size * q["columns"]
                    w = p.width - 2 * p.margin_x
                    top_lanes = [
                        (p.margin_x, 8 + i * (h + 4), w, h, 0)
                        for i in range(max(1, int((p.margin_top - 16) / (h + 4))))
                        if 8 + i * (h + 4) + h <= p.margin_top - 8
                    ]
                bands = top_lanes
            else:
                bands = candidates[first_lane:] if pi == start_page else candidates
            for k, lane in enumerate(bands):
                x, y, w, h, _ = lane
                if x < 4 or y < 4 or x + w > p.width - 4 or y + h > p.height - 4:
                    continue
                obstacles = [ink(g) for g in pages[pi].glyphs] + [
                    rect(b) for b in boxes[pi]
                ]
                start = (
                    (anchor.y if p.vertical else anchor.x)
                    if q["kind"] != "top" and pi == start_page and k == 0
                    else (y if p.vertical else x)
                )
                intervals = free_intervals(lane, p, obstacles, start)
                for lo, hi in intervals:
                    cap = min(q["extent"], int((hi - lo) / step))
                    if cap < 1:
                        continue
                    count = min(len(chars) - cursor, cap * q["columns"])
                    rows = math.ceil(count / q["columns"])
                    gx, gy = (x, lo) if p.vertical else (lo, y)
                    if q["kind"] == "top":
                        gy = hi - rows * step if p.vertical else y
                    body = [
                        g
                        for g in pages[pi].glyphs
                        if g.block >= 0
                        and layout.book.blocks[g.block].inlines[g.inline].kind
                        in {"text", "emphasis"}
                    ]
                    if first_fragment and pi == start_page:
                        target = anchor
                    else:
                        target = (
                            min(
                                body,
                                key=lambda g: abs(g.x - (lane[4] if p.vertical else gx))
                                + abs(g.y - (gy if p.vertical else lane[4])),
                            )
                            if body
                            else False
                        )
                    # False signals a continuation-only page in the Word adapter.
                    box = emit(
                        q,
                        pi,
                        gx,
                        gy,
                        size,
                        q["columns"],
                        rows,
                        chars[cursor : cursor + count],
                        chars[cursor][0],
                        part,
                        anchor=target if target else anchor,
                    )
                    if not body:
                        boxes[pi][-1] = replace(box, block=-1, inline=0, offset=0)
                    cursor += count
                    part += 1
                    first_fragment = False
                    if cursor >= len(chars):
                        break
                if cursor >= len(chars):
                    break
            if cursor == progress and pi >= original_count:
                raise BambooError("续批页也无法容纳批注，请调整留白、列数或字号")
            pi += 1
        if pi - 1 >= original_count:
            warnings.append(
                "部分长批注已排入后续批注页；修改正文后会重新计算续排位置。"
            )
    result = replace(
        layout,
        pages=tuple(
            replace(
                page, glyphs=page.glyphs + tuple(added[i]), annotations=tuple(boxes[i])
            )
            for i, page in enumerate(pages)
        ),
        warnings=tuple(dict.fromkeys(warnings)),
    )
    # Independent conservation across fragments, including continuation pages.
    for q in requests:
        expected = {o for o, _ in clusters(q["text"])}
        actual = [
            g.offset
            for page in result.pages
            for g in page.glyphs
            if g.annotation_id == q["id"]
        ]
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise BambooError("批注续排文字守恒检查失败")
    return result
