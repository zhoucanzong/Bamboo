"""Pure grid composition, independent of file formats and installed fonts."""

from __future__ import annotations

import math
import unicodedata

from .model import BambooError, Book, Glyph, Layout, Line, Page, Polygon

PUNCTUATION = frozenset("，。、；：！？,.!?;:")
OPENING = frozenset("（〔［｛〈《「『【〖‘“")
CLOSING = frozenset("）〕］｝〉》」』】〗’”，。、；：！？,.!?;:")
VERTICAL = str.maketrans(
    "（）〔〕［］｛｝〈〉《》「」『』【】…—", "︵︶︹︺﹇﹈︷︸︿﹀︽︾﹁﹂﹃﹄︻︼︙︱"
)


def clusters(text):
    """Preserve base + combining marks / variation selectors and source offsets.

    This is intentionally CJK-focused, not a full Unicode grapheme algorithm.
    """
    result = []
    for offset, char in enumerate(text):
        if result and (
            unicodedata.combining(char)
            or 0xFE00 <= ord(char) <= 0xFE0F
            or 0xE0100 <= ord(char) <= 0xE01EF
        ):
            old_offset, old_text = result[-1]
            result[-1] = old_offset, old_text + char
        else:
            result.append((offset, char))
    return result


def chinese_number(n):
    digits = "〇一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n < 100:
        return (
            (digits[n // 10] if n >= 20 else "")
            + "十"
            + (digits[n % 10] if n % 10 else "")
        )
    return "".join(digits[int(c)] for c in str(n))


def _frame(book, number):
    p = book.profile
    glyphs, lines, polygons = [], [], []
    x0, y0 = p.margin_x, p.margin_top
    x1, y1 = p.width - p.margin_x, p.height - p.margin_bottom

    def rect(left, top, right, bottom, weight):
        for a, b, c, d in (
            (left, top, right, top),
            (right, top, right, bottom),
            (right, bottom, left, bottom),
            (left, bottom, left, top),
        ):
            lines.append(Line(a, b, c, d, weight, p.rule_color))

    if p.border != "none":
        rect(x0, y0, x1, y1, 0.8)
        if p.border == "double":
            rect(x0 - 4, y0 - 4, x1 + 4, y1 + 4, 1.5)
    spine_x = x0 + p.panel_width if p.panels == 2 else x0
    panel_starts = [x0, spine_x + p.spine] if p.panels == 2 else [x0 + p.spine]
    for start in panel_starts:
        if p.rules:
            for col in range(1, p.columns):
                if p.vertical:
                    xx = start + col * p.line_advance
                    lines.append(Line(xx, y0, xx, y1, 0.35, p.rule_color))
                else:
                    yy = y0 + col * p.line_advance
                    lines.append(
                        Line(start, yy, start + p.panel_width, yy, 0.35, p.rule_color)
                    )
    if p.spine == 0:
        return glyphs, lines, polygons
    if p.spine_rules:
        for xx in (spine_x, spine_x + p.spine):
            lines.append(Line(xx, y0, xx, y1, 0.7, p.rule_color))

    def spine_text(text, top, available, size=12):
        chars = [c for _, c in clusters(text) if not c.isspace()]
        if not chars:
            return
        cell = min(size * 1.5, available / len(chars))
        actual = min(size, cell * 0.8, p.spine * 0.65)
        if actual < 4:
            raise BambooError("版心文字过长或版心过窄，无法在可读字号下排入")
        for i, char in enumerate(chars):
            glyphs.append(
                Glyph(
                    char,
                    spine_x,
                    top + i * cell,
                    p.spine,
                    cell,
                    actual,
                    "spine",
                    color=p.ink,
                )
            )

    if p.show_title:
        spine_text(book.title, y0 + p.body_height * 0.15, p.body_height * 0.32)
    if p.show_volume:
        spine_text(book.volume, y0 + p.body_height * 0.52, p.body_height * 0.19, 11)
    if p.show_page_number:
        spine_text(
            chinese_number(number), y0 + p.body_height * 0.83, p.body_height * 0.13, 11
        )
    if p.fish_tail:
        from .symbols import fish_tail

        for index, yy in enumerate(
            (y0 + p.body_height * 0.09, y0 + p.body_height * 0.76)
        ):
            direction = (
                ("down" if index == 0 else "up")
                if p.fish_tail_direction == "auto"
                else p.fish_tail_direction
            )
            extra_lines, extra_polygons = fish_tail(
                p.fish_tail_style,
                direction,
                spine_x + p.spine / 2,
                yy,
                min(p.spine * 0.7, p.body_height * 0.05),
                p.ink,
            )
            lines.extend(extra_lines)
            polygons.extend(extra_polygons)
    return glyphs, lines, polygons


def compose(book: Book) -> Layout:
    p = book.profile
    cross, step = p.line_advance, p.cell_advance
    pages, warnings, block_starts = [], [], []
    glyphs, lines, polygons = _frame(book, 1)
    col, row, has_body = 0, 0, False
    last = None
    note_number = 0

    def box_border(items):
        if not items:
            return
        if p.vertical:
            left = min(g.x + (g.width - g.size) / 2 for g in items) - 2
            right = max(g.x + (g.width + g.size) / 2 for g in items) + 2
            top = min(g.y for g in items) + 1
            bottom = max(g.y + g.height for g in items) - 1
        else:
            left = min(g.x for g in items) + 1
            right = max(g.x + g.width for g in items) - 1
            top = min(g.y + (g.height - g.size) / 2 for g in items) - 2
            bottom = max(g.y + (g.height + g.size) / 2 for g in items) + 2
        for a, b, c, d in [
            (left, top, right, top),
            (right, top, right, bottom),
            (right, bottom, left, bottom),
            (left, bottom, left, top),
        ]:
            lines.append(Line(a, b, c, d, 0.55, p.ink))

    def new_page():
        nonlocal glyphs, lines, polygons, col, row, has_body, last
        if has_body:
            pages.append(
                Page(len(pages) + 1, tuple(glyphs), tuple(lines), tuple(polygons))
            )
        glyphs, lines, polygons = _frame(book, len(pages) + 1)
        col, row, has_body, last = 0, 0, False, None

    def advance():
        nonlocal col, row, last
        col += 1
        row, last = 0, None
        if col >= p.columns * p.panels:
            new_page()

    def position():
        if not p.vertical:
            panel, inner = divmod(col, p.columns)
            start = p.margin_x + (
                p.spine if p.panels == 1 else panel * (p.panel_width + p.spine)
            )
            return start + row * step, p.margin_top + inner * cross
        if p.panels == 1:
            return (
                p.width - p.margin_x - (col + 1) * p.column_width,
                p.margin_top + row * p.row_height,
            )
        panel, inner = divmod(col, p.columns)
        right = p.width - p.margin_x if panel == 0 else p.margin_x + p.panel_width
        return right - (inner + 1) * p.column_width, p.margin_top + row * p.row_height

    for bi, block in enumerate(book.blocks):
        if block.kind == "pagebreak":
            if has_body:
                new_page()
            continue
        if row > 0:
            advance()
        # A short heading must have room for a following body column on the same page.
        if block.kind == "heading" and col == p.columns * p.panels - 1 and has_body:
            new_page()
        row, last = block.indent, None
        x, y = position()
        block_starts.append(
            {
                "block": bi,
                "page": len(pages),
                "x": x,
                "y": y,
                "width": cross if p.vertical else step,
                "height": step if p.vertical else cross,
            }
        )
        has_body = True
        if not block.inlines:
            has_body = True
            row = max(row, 1)
        queued_notes = []
        for ii, inline in enumerate(block.inlines):
            chars = [
                (offset, char)
                for offset, char in clusters(inline.text)
                if char not in "\n\r\t"
            ]
            if inline.kind == "ruby" and row + len(chars) > p.rows:
                advance()
            if inline.kind == "numbered_note":
                note_number += 1
                marker = f"【{chinese_number(note_number)}】"
                slots = min(2, p.rows)
                if row + slots > p.rows:
                    advance()
                x, y = position()
                mini = slots * step / len(marker)
                for j, char in enumerate(marker):
                    glyphs.append(
                        Glyph(
                            char.translate(VERTICAL) if p.vertical else char,
                            x if p.vertical else x + j * mini,
                            y + j * mini if p.vertical else y,
                            cross if p.vertical else mini,
                            mini if p.vertical else cross,
                            min(p.font_size * 0.6, mini * 0.85),
                            "note_reference",
                            -2,
                            reference_id=inline.target,
                            color=p.ink,
                        )
                    )
                row += slots
                last = None
                queued_notes.append((ii, inline, note_number))
                continue
            label_items = []
            if inline.kind == "label":
                if len(chars) > p.rows:
                    raise BambooError("标签不能放入一栏，请增加字格数量")
                if row + len(chars) > p.rows:
                    advance()
            if inline.kind in {"note", "footnote"}:
                remaining = chars
                while remaining:
                    if row >= p.rows:
                        advance()
                    count = min(len(remaining), (p.rows - row) * 4)
                    chunk, remaining = remaining[:count], remaining[count:]
                    used_rows = math.ceil(count / 4)
                    right_count = math.ceil(count / 2)
                    x, y = position()
                    for j, (offset, char) in enumerate(chunk):
                        subcol = 0 if j < right_count else 1
                        subrow = j if subcol == 0 else j - right_count
                        if p.vertical:
                            gx, gy, gw, gh = (
                                x + cross * (0.5 if subcol == 0 else 0.1),
                                y + subrow * step / 2,
                                cross * 0.4,
                                step / 2,
                            )
                        else:
                            gx, gy, gw, gh = (
                                x + subrow * step / 2,
                                y + cross * (0.1 if subcol == 0 else 0.5),
                                step / 2,
                                cross * 0.4,
                            )
                        glyphs.append(
                            Glyph(
                                char.translate(VERTICAL) if p.vertical else char,
                                gx,
                                gy,
                                gw,
                                gh,
                                p.font_size * 0.5,
                                inline.kind,
                                bi,
                                ii,
                                offset,
                                p.ink,
                            )
                        )
                    row += used_rows
                    has_body = True
                    last = None
                continue
            for ci, (offset, char) in enumerate(chars):
                if (
                    char in PUNCTUATION
                    and p.punctuation == "hide"
                    and inline.kind != "label"
                ):
                    continue
                if (
                    char in PUNCTUATION
                    and p.punctuation == "judou"
                    and last is not None
                    and inline.kind != "label"
                ):
                    gx = last.x + last.width * 0.72
                    gy = last.y + last.height * 0.56
                    mark = "。" if char in "。.!?！？" else "、"
                    glyphs.append(
                        Glyph(
                            mark,
                            gx,
                            gy,
                            last.width * 0.23,
                            last.height * 0.4,
                            p.font_size * 0.38,
                            "punctuation",
                            bi,
                            ii,
                            offset,
                            p.ink,
                        )
                    )
                    last = None  # Consecutive marks get a real cell, never overlap.
                    continue
                if row >= p.rows:
                    advance()
                next_char = chars[ci + 1][1] if ci + 1 < len(chars) else ""
                if (
                    p.punctuation == "keep"
                    and row == p.rows - 1
                    and p.rows > 1
                    and (char in OPENING or next_char in CLOSING)
                ):
                    advance()
                if p.punctuation == "keep" and row == 0 and char in CLOSING:
                    warnings.append(f"段 {bi+1} 字 {offset+1}: 栏首出现闭合标点")
                x, y = position()
                role = block.kind if block.kind in {"heading", "commentary"} else "body"
                color = p.accent if inline.kind == "emphasis" else p.ink
                g = Glyph(
                    char.translate(VERTICAL) if p.vertical else char,
                    x,
                    y,
                    cross if p.vertical else step,
                    step if p.vertical else cross,
                    p.font_size
                    * (
                        0.65
                        if inline.kind == "label"
                        else 0.75 if block.kind == "commentary" else 1
                    ),
                    "label" if inline.kind == "label" else role,
                    bi,
                    ii,
                    offset,
                    color,
                )
                glyphs.append(g)
                if inline.kind == "label":
                    label_items.append(g)
                if inline.kind == "emphasis":
                    if p.vertical:
                        xx = x + cross * 0.82
                        lines.append(
                            Line(xx, y + step * 0.2, xx, y + step * 0.8, 0.75, p.accent)
                        )
                    else:
                        yy = y + cross * 0.82
                        lines.append(
                            Line(x + step * 0.2, yy, x + step * 0.8, yy, 0.75, p.accent)
                        )
                row += 1
                has_body, last = True, g
            if inline.boxed:
                box_border(label_items)
        for ii, note, number in queued_notes:
            if row > 0:
                advance()
            small_step = step * 0.72
            capacity = max(
                1, int((p.body_height if p.vertical else p.panel_width) / small_step)
            )
            cursor = 0

            def emit_note(text, role, source=False):
                nonlocal cursor, row, has_body
                emitted = []
                for offset, char in clusters(text):
                    if char in "\n\r\t":
                        continue
                    if cursor >= capacity:
                        advance()
                        cursor = 0
                    x, y = position()
                    if p.vertical:
                        y += cursor * small_step
                    else:
                        x += cursor * small_step
                    g = Glyph(
                        char.translate(VERTICAL) if p.vertical else char,
                        x,
                        y,
                        cross if p.vertical else small_step,
                        small_step if p.vertical else cross,
                        p.font_size * 0.65,
                        role,
                        bi if source else -2,
                        ii if source else -1,
                        offset if source else -1,
                        p.ink,
                        reference_id=note.target,
                    )
                    glyphs.append(g)
                    emitted.append(g)
                    cursor += 1
                    has_body = True
                return emitted

            emit_note(f"【{chinese_number(number)}】", "note_number")
            if note.annotation:
                if len(note.annotation) > capacity:
                    raise BambooError("注家标签不能放入一栏，请增加字格数量")
                if cursor + len(note.annotation) > capacity:
                    advance()
                    cursor = 0
                label_glyphs = emit_note(note.annotation, "note_label")
                if note.boxed:
                    box_border(label_glyphs)
            emit_note(note.text, "numbered_note", True)
            row = 1
    if has_body:
        pages.append(Page(len(pages) + 1, tuple(glyphs), tuple(lines), tuple(polygons)))
    if not pages:
        raise BambooError("正文经排版规则处理后为空")
    result = Layout(
        book, tuple(pages), tuple(dict.fromkeys(warnings)), tuple(block_starts)
    )
    from .annotations import add_annotations

    result = add_annotations(result)
    validate_layout(result)
    return result


def validate_layout(layout):
    p = layout.book.profile
    seen = set()
    for page in layout.pages:
        annotation_expected = {
            (box.id, offset)
            for box in page.annotations
            for offset, _ in clusters(box.text)
        }
        annotation_seen = []
        for g in page.glyphs:
            if (
                g.x < -1e-6
                or g.y < -1e-6
                or g.x + g.width > p.width + 1e-6
                or g.y + g.height > p.height + 1e-6
            ):
                raise BambooError(f"第 {page.number} 页存在越界文字: {g.text}")
            if g.block >= 0:
                key = g.block, g.inline, g.offset
                if key in seen:
                    raise BambooError(f"源文字被重复排入: {key}")
                seen.add(key)
            if g.annotation_id:
                annotation_seen.append((g.annotation_id, g.offset))
        if (
            len(set(annotation_seen)) != len(annotation_seen)
            or set(annotation_seen) != annotation_expected
        ):
            raise BambooError(f"第 {page.number} 页批注文字守恒检查失败")
    expected = set()
    for bi, block in enumerate(layout.book.blocks):
        for ii, inline in enumerate(block.inlines):
            for offset, char in clusters(inline.text):
                if char in "\n\r\t" or (
                    inline.kind not in {"note", "footnote", "numbered_note", "label"}
                    and char in PUNCTUATION
                    and p.punctuation == "hide"
                ):
                    continue
                expected.add((bi, ii, offset))
    if seen != expected:
        raise BambooError(
            f"文字守恒检查失败: 遗漏 {len(expected-seen)}，多出 {len(seen-expected)}"
        )
