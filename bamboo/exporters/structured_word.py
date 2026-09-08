"""Native editable tables for specialist records, with tagged live fields."""

from dataclasses import replace
from docx.shared import Pt
from docx.enum.table import (
    WD_TABLE_ALIGNMENT,
    WD_ROW_HEIGHT_RULE,
    WD_CELL_VERTICAL_ALIGNMENT,
)
from docx.oxml.ns import qn
from .wordflow import element, _run, _section, _styles


def tagged(paragraph, value, font, size, color, tag=None):
    run = _run(paragraph, value, font, size, color)
    if tag:
        sdt = element("w:sdt")
        props = element("w:sdtPr")
        props.append(element("w:tag", val=tag))
        sdt.append(props)
        content = element("w:sdtContent")
        sdt.append(content)
        paragraph._p.remove(run._r)
        content.append(run._r)
        paragraph._p.append(sdt)


def table(doc, widget, font, p, kind):
    t = doc.add_table(rows=widget["rows"], cols=widget["columns"])
    t.autofit = False
    t.alignment = WD_TABLE_ALIGNMENT.LEFT
    pr = t._tbl.tblPr
    pr.append(element("w:tblInd", w=0, type="dxa"))
    borders = element("w:tblBorders")
    for name in ["top", "left", "bottom", "right", "insideH", "insideV"]:
        borders.append(
            element(
                "w:" + name,
                val="single" if p.border != "none" else "nil",
                sz=5,
                color=p.rule_color[1:],
            )
        )
    pr.append(borders)
    margins = element("w:tblCellMar")
    for side in ["top", "left", "bottom", "right"]:
        margins.append(element("w:" + side, w=80, type="dxa"))
    pr.append(margins)
    for c, w in zip(t.columns, widget["widths"]):
        c.width = Pt(w)
    for ri, row in enumerate(t.rows):
        row.height = Pt(max(8, widget["heights"][ri] - 8))
        row.height_rule = WD_ROW_HEIGHT_RULE.AT_LEAST
        row._tr.get_or_add_trPr().append(element("w:cantSplit"))
        for ci, c in enumerate(row.cells):
            c.width = Pt(widget["widths"][ci])
            c.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.TOP
    for raw in widget["cells"]:
        c = t.cell(raw["row"], raw["column"])
        pp = c.paragraphs[0]
        pp.paragraph_format.space_before = pp.paragraph_format.space_after = Pt(0)
        pp.paragraph_format.line_spacing = Pt(raw["size"] * 1.35)
        if raw["vertical"]:
            c._tc.get_or_add_tcPr().append(element("w:textDirection", val="tbRlV"))
        pp._p.get_or_add_pPr().append(element("w:snapToGrid", val="0"))
        tag = (
            f'bamboo:{kind}:{raw["record"]}:{raw["field"]}'
            if raw.get("record") and raw.get("editable", True)
            else None
        )
        tagged(pp, raw["text"], font, raw["size"], raw["color"], tag)
    if not p.vertical:
        t.rows[0]._tr.get_or_add_trPr().append(element("w:tblHeader"))
    return t


def write_structured(doc, layout, font):
    p = layout.book.profile
    _styles(doc, font, p)
    native = p.updated(
        writing_mode="horizontal-tb",
        panels=1,
        spine=0,
        columns=1,
        rows=1,
        font_size=min(12, p.font_size),
    )
    _section(doc.sections[0], native)
    sec = doc.sections[0]
    grid = sec._sectPr.find(qn("w:docGrid"))
    if grid is not None:
        sec._sectPr.remove(grid)
    sec.top_margin = Pt(12)
    sec.bottom_margin = Pt(10)
    sec.left_margin = sec.right_margin = Pt(p.margin_x)
    for pi, page in enumerate(layout.pages):
        first = True
        for widget in page.widgets:
            if widget["kind"] == "table":
                table(doc, widget, font, p, layout.book.special.kind)
                continue
            para = doc.add_paragraph()
            para.paragraph_format.space_before = para.paragraph_format.space_after = Pt(
                0
            )
            para.paragraph_format.line_spacing = Pt(widget["height"])
            if first:
                para.paragraph_format.page_break_before = pi > 0
                first = False
            tag = "bamboo:meta:title" if widget["text"] == layout.book.title else None
            tagged(para, widget["text"], font, widget["size"], widget["color"], tag)
    # Column/table contents, including vertical cells, remain native text.


def import_structured(doc, saved):
    from ..structured import GiftRecord, GiftLedger
    from ..editor import EditorSession
    from ..model import Book, Block, BambooError

    if not isinstance(saved.special, GiftLedger):
        return None
    values = {}
    order = []
    title = None
    for sdt in doc._element.body.iter(qn("w:sdt")):
        tag = sdt.find(qn("w:sdtPr"))
        tag = tag.find(qn("w:tag")) if tag is not None else None
        key = tag.get(qn("w:val"), "") if tag is not None else ""
        value = "".join(
            (n.text or "") if n.tag == qn("w:t") else "\n"
            for n in sdt.iter()
            if n.tag in {qn("w:t"), qn("w:br")}
        )
        if key == "bamboo:meta:title":
            title = title or value
        if key.startswith("bamboo:gift:"):
            _, _, record, field = key.split(":")
            if field not in {"name", "amount", "gift", "date", "note"}:
                continue
            if record not in values:
                values[record] = {}
                order.append(record)
            values[record][field] = value
    if not values and saved.special.records:
        return None
    if saved.profile.vertical:
        order = []
        for t in doc.tables:
            local = []
            for node in t._tbl.iter(qn("w:tag")):
                key = node.get(qn("w:val"), "")
                if key.startswith("bamboo:gift:"):
                    record = key.split(":")[2]
                    if record not in local:
                        local.append(record)
            order.extend(reversed(local))
    try:
        records = tuple(GiftRecord(id=i, **values[i]) for i in order)
        special = replace(saved.special, records=records)
        book = Book(
            title or doc.core_properties.title or saved.title,
            (Block(),),
            volume=saved.volume,
            author=doc.core_properties.author or saved.author,
            profile=saved.profile,
            special=special,
        )
        return EditorSession(book), [
            "礼簿已按 Word 中的实际记录导入，金额大写与合计已重新计算。"
        ]
    except (BambooError, TypeError, KeyError):
        return None
