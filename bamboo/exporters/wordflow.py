"""Native Word stories: direction-preserving text, double-line notes and footnotes.

No automatic page/column breaks or glyph text boxes are synthesized here. Word
owns reflow; source page breaks are the only explicit pagination instructions.
"""

from docx.enum.style import WD_STYLE_TYPE
from docx.enum.text import WD_LINE_SPACING
from docx.enum.section import WD_ORIENT, WD_SECTION_START
from docx.oxml import OxmlElement
from docx.oxml.ns import qn, nsmap
from docx.shared import Pt, RGBColor
from docx.opc.part import Part
from docx.opc.packuri import PackURI
from docx.opc.constants import RELATIONSHIP_TYPE as RT
from lxml import etree
from docx.text.paragraph import Paragraph

from ..layout import PUNCTUATION, clusters


def element(tag, **attrs):
    node = OxmlElement(tag)
    for key, value in attrs.items():
        node.set(qn("w:" + key), str(value))
    return node


def set_font(properties, family, size):
    fonts = properties.find(qn("w:rFonts"))
    if fonts is None:
        fonts = element("w:rFonts")
        properties.insert(0, fonts)
    for attr in list(fonts.attrib):
        if attr.endswith("Theme"):
            del fonts.attrib[attr]
    for name in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn("w:" + name), family)
    for tag in ("w:sz", "w:szCs"):
        old = properties.find(qn(tag))
        if old is not None:
            properties.remove(old)
        properties.append(element(tag, val=round(size * 2)))
    properties.append(element("w:lang", val="zh-TW", eastAsia="zh-TW"))


def clean_styles(doc):
    for root in (doc.styles._element, doc._element):
        for border in list(root.iter(qn("w:pBdr"))):
            border.getparent().remove(border)
        for fonts in root.iter(qn("w:rFonts")):
            for attr in list(fonts.attrib):
                if attr.endswith("Theme"):
                    del fonts.attrib[attr]


def line_pitch(profile):
    # Floating wrap regions include a small amount of line-box leading in Word
    # readers. This tolerance prevents a whole line being lost beside the spine.
    return (
        profile.line_advance - min(0.4, profile.line_advance * 0.02)
        if profile.vertical and profile.panels == 2 and profile.spine
        else profile.line_advance
    )


def _styles(doc, font, p):
    if "Bamboo Label" not in doc.styles:
        doc.styles.add_style("Bamboo Label", WD_STYLE_TYPE.CHARACTER)
    if "Bamboo Note Padding" not in doc.styles:
        doc.styles.add_style("Bamboo Note Padding", WD_STYLE_TYPE.CHARACTER)
    for name, size in (
        ("Normal", p.font_size),
        ("Bamboo Commentary", p.font_size * 0.75),
        ("Bamboo Numbered Note", p.font_size * 0.65),
        ("Bamboo Footnote", p.font_size * 0.6),
    ):
        style = (
            doc.styles[name]
            if name in doc.styles
            else doc.styles.add_style(name, WD_STYLE_TYPE.PARAGRAPH)
        )
        set_font(style._element.get_or_add_rPr(), font.family, size)
        style.font.color.rgb = RGBColor.from_string(p.ink[1:])
        fmt = style.paragraph_format
        fmt.space_before = fmt.space_after = Pt(0)
        fmt.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        fmt.line_spacing = Pt(
            line_pitch(p) if name != "Bamboo Footnote" else line_pitch(p) * 0.7
        )
        fmt.widow_control = False
        fmt.keep_together = False
    for level in range(1, 10):
        style = doc.styles[f"Heading {level}"]
        set_font(style._element.get_or_add_rPr(), font.family, p.font_size)
        style.font.color.rgb = RGBColor.from_string(p.ink[1:])
        style.font.bold = False
        style.paragraph_format.space_before = style.paragraph_format.space_after = Pt(0)
        style.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        style.paragraph_format.line_spacing = Pt(line_pitch(p))


def _section(section, profile):
    p = profile
    section.orientation = (
        WD_ORIENT.LANDSCAPE if p.width > p.height else WD_ORIENT.PORTRAIT
    )
    section.page_width, section.page_height = Pt(p.width), Pt(p.height)
    section.top_margin, section.bottom_margin = Pt(p.margin_top), Pt(p.margin_bottom)
    section.left_margin = Pt(p.margin_x + (p.spine if p.panels == 1 else 0))
    section.right_margin = Pt(p.margin_x)
    section.header_distance = section.footer_distance = Pt(0)
    sp = section._sectPr
    for name in ("w:docGrid", "w:textDirection", "w:pgBorders"):
        old = sp.find(qn(name))
        if old is not None:
            sp.remove(old)
    sp.append(element("w:textDirection", val="tbRl" if p.vertical else "lrTb"))
    numbering = sp.find(qn("w:pgNumType"))
    if numbering is None:
        numbering = element("w:pgNumType")
        sp.append(numbering)
    numbering.set(qn("w:fmt"), "chineseCounting")
    sp.append(
        element(
            "w:docGrid",
            type="linesAndChars",
            linePitch=round(line_pitch(p) * 20),
            charSpace=round((p.cell_advance - p.font_size) * 4096),
        )
    )
    # Horizontal multi-panel flow is ordinary newspaper columns. In a vertical
    # section Word columns would create TOP/BOTTOM bands, so never use them there.
    cols = sp.find(qn("w:cols"))
    cols.set(qn("w:num"), str(p.panels if not p.vertical else 1))
    cols.set(qn("w:space"), str(round(p.spine * 20)))


def _run(
    paragraph, text, font, size, color, pitch=None, combine_id=None, raise_by=None
):
    run = paragraph.add_run(text)
    rp = run._element.get_or_add_rPr()
    set_font(rp, font.family, size)
    run.font.color.rgb = RGBColor.from_string(color[1:])
    rp.append(element("w:snapToGrid", val="0"))
    if pitch is not None:
        rp.append(element("w:spacing", val=round((pitch - size) * 20)))
    if combine_id is not None:
        rp.append(element("w:eastAsianLayout", id=combine_id, combine="1"))
    if raise_by is not None:
        rp.append(element("w:position", val=round(raise_by * 2)))
    return run


def _text(paragraph, text, font, p, size, color):
    if "\n" in text:
        for i, line in enumerate(text.split("\n")):
            if i:
                paragraph.add_run().add_break()
            if line:
                _text(paragraph, line, font, p, size, color)
        return
    chars = [c for _, c in clusters(text) if c not in "\r\t"]
    if p.punctuation == "hide":
        _run(
            paragraph,
            "".join(c for c in chars if c not in PUNCTUATION),
            font,
            size,
            color,
            p.cell_advance,
        )
        return
    if p.punctuation == "keep":
        _run(paragraph, "".join(chars), font, size, color, p.cell_advance)
        return
    # Small, raised punctuation shares the previous character's advance. Runs
    # remain native text; this does not pin them to a page or column coordinate.
    buffer, i = [], 0
    while i < len(chars):
        if (
            i + 1 < len(chars)
            and chars[i] not in PUNCTUATION
            and chars[i + 1] in PUNCTUATION
        ):
            if buffer:
                _run(paragraph, "".join(buffer), font, size, color, p.cell_advance)
                buffer = []
            small = round(size * 0.38 * 2) / 2
            _run(paragraph, chars[i], font, size, color, p.cell_advance - small)
            mark = "。" if chars[i + 1] in "。.!?！？" else "、"
            _run(paragraph, mark, font, small, color, small, raise_by=size * 0.42)
            i += 2
        else:
            buffer.append(chars[i])
            i += 1
    if buffer:
        _run(paragraph, "".join(buffer), font, size, color, p.cell_advance)


def _ruby(paragraph, inline, font, p, size):
    ruby = element("w:ruby")
    props = element("w:rubyPr")
    for name, value in (
        ("rubyAlign", "distributeSpace"),
        ("hps", round(size)),
        ("hpsRaise", round(size * 1.1)),
        ("hpsBaseText", round(size * 2)),
        ("lid", "zh-TW"),
    ):
        props.append(element("w:" + name, val=value))
    ruby.append(props)
    for tag, text, point, color in (
        ("rt", inline.annotation, size * 0.5, p.accent),
        ("rubyBase", inline.text, size, p.ink),
    ):
        group = element("w:" + tag)
        r = element("w:r")
        rp = element("w:rPr")
        set_font(rp, font.family, point)
        rp.append(element("w:color", val=color[1:]))
        r.append(rp)
        t = element("w:t")
        t.text = text
        r.append(t)
        group.append(r)
        ruby.append(group)
    paragraph.add_run()._element.append(ruby)


def _anchored_textbox(paragraph, box, paragraph_glyph, font, profile, serial):
    """Editable paragraph-relative annotation frame with explicit writing axes.

    Short ruby follows individual characters. Long frames follow their paragraph;
    editors need to regenerate geometry after edits inside the anchored paragraph.
    """
    v = "urn:schemas-microsoft-com:vml"
    pict = OxmlElement("w:pict")
    shape = etree.SubElement(
        pict, "{" + v + "}rect", id=f"BambooAnnotation{serial}", stroked="f", filled="f"
    )
    if profile.vertical:
        if box.kind == "top":
            left, top, hrel, vrel = (
                box.y,
                profile.width - box.x - box.width,
                "page",
                "page",
            )
        else:
            left = box.y - paragraph_glyph.y
            top = paragraph_glyph.x + paragraph_glyph.width - box.x - box.width
            hrel, vrel = "char", "line"
    else:
        if box.kind == "top":
            left, top, hrel, vrel = box.x, box.y, "page", "page"
        else:
            left, top = box.x - paragraph_glyph.x, box.y - paragraph_glyph.y
            hrel, vrel = "char", "line"
    shape.set(
        "style",
        f"position:absolute;margin-left:{left}pt;margin-top:{top}pt;"
        f"width:{box.width}pt;height:{box.height}pt;"
        f"mso-position-horizontal-relative:{hrel};mso-position-vertical-relative:{vrel};z-index:{serial}",
    )
    textbox = etree.SubElement(
        shape,
        "{" + v + "}textbox",
        inset="0,0,0,0",
        style="layout-flow:vertical" if profile.vertical else "layout-flow:horizontal",
    )
    content = OxmlElement("w:txbxContent")
    textbox.append(content)
    pp = OxmlElement("w:p")
    content.append(pp)
    native = Paragraph(pp, paragraph._parent)
    native.paragraph_format.space_before = native.paragraph_format.space_after = Pt(0)
    native.paragraph_format.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    native.paragraph_format.line_spacing = Pt(box.size)
    _run(native, box.text, font, box.size, profile.accent, box.size * 1.2)
    paragraph.add_run()._element.append(pict)


class Footnotes:
    def __init__(self, doc, font, profile):
        self.doc, self.font, self.profile = doc, font, profile
        self.root = etree.Element(qn("w:footnotes"), nsmap={"w": nsmap["w"]})
        for index, kind in ((-1, "separator"), (0, "continuationSeparator")):
            note = element("w:footnote", id=index, type=kind)
            p = element("w:p")
            r = element("w:r")
            r.append(element("w:" + kind))
            p.append(r)
            note.append(p)
            self.root.append(note)
        self.count = 0

    def add(self, paragraph, text):
        self.count += 1
        run = paragraph.add_run()
        rp = run._element.get_or_add_rPr()
        set_font(rp, self.font.family, self.profile.font_size * 0.6)
        rp.append(element("w:vertAlign", val="superscript"))
        run._element.append(element("w:footnoteReference", id=self.count))
        note = element("w:footnote", id=self.count)
        para = element("w:p")
        pp = element("w:pPr")
        pp.append(element("w:pStyle", val="BambooFootnote"))
        para.append(pp)
        r = element("w:r")
        rp = element("w:rPr")
        set_font(rp, self.font.family, self.profile.font_size * 0.6)
        rp.append(element("w:vertAlign", val="superscript"))
        r.append(rp)
        r.append(element("w:footnoteRef"))
        para.append(r)
        r = element("w:r")
        rp = element("w:rPr")
        set_font(rp, self.font.family, self.profile.font_size * 0.6)
        r.append(rp)
        t = element("w:t")
        t.set(qn("xml:space"), "preserve")
        t.text = " " + text
        r.append(t)
        para.append(r)
        note.append(para)
        self.root.append(note)

    def finish(self):
        if not self.count:
            return
        part = Part(
            PackURI("/word/footnotes.xml"),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.footnotes+xml",
            etree.tostring(self.root, xml_declaration=True, encoding="UTF-8"),
            self.doc.part.package,
        )
        self.doc.part.relate_to(part, RT.FOOTNOTES)


def write_flow(doc, layout, font, decorate=None):
    from .wordnotes import NumberedNotes, boxed_label

    p = layout.book.profile
    _styles(doc, font, p)
    from ..styles import section_ranges, resolve_style
    from .wordstyles import register_styles, format_paragraph, write_cover, inline_seal

    register_styles(doc, layout.book, font)
    ranges = section_ranges(layout.book)
    boundaries = {begin: (end, spec) for begin, end, spec in ranges}
    covers = set()
    footnotes = Footnotes(doc, font, p)
    numbered = NumberedNotes(doc, font, p)
    pending_break = False
    previous = None
    note_id = 0
    boxes = [b for page in layout.pages for b in page.annotations if b.kind != "ruby"]
    glyphs = {
        (g.block, g.inline, g.offset): g
        for page in layout.pages
        for g in page.glyphs
        if g.block >= 0
    }
    paragraph_glyphs = {}
    for page in layout.pages:
        for g in page.glyphs:
            if g.block >= 0:
                paragraph_glyphs.setdefault(g.block, g)
    shape_id = 30000
    for bi, block in enumerate(layout.book.blocks):
        if bi in boundaries:
            end, spec = boundaries[bi]
            p = spec.profile
            section = (
                doc.sections[0]
                if bi == 0
                else doc.add_section(WD_SECTION_START.NEW_PAGE)
            )
            _section(section, p)
            if bi > 0:
                section.header.is_linked_to_previous = False
                section.footer.is_linked_to_previous = False
            if spec.page_number_start is not None:
                section._sectPr.find(qn("w:pgNumType")).set(
                    qn("w:start"), str(spec.page_number_start)
                )
            else:
                section._sectPr.find(qn("w:pgNumType")).attrib.pop(qn("w:start"), None)
            pending_break = False
            previous = None
            footnotes.profile = p
            numbered.profile = p
            if spec.page_type == "title-slip":
                write_cover(doc, layout.book, bi, end, spec, font, layout)
                covers.update(range(bi, end))
            elif decorate is not None:
                decorate(section, bi, end, spec)
        if bi in covers:
            continue
        if block.kind == "pagebreak":
            pending_break = previous is not None
            continue
        style = (
            f"Heading {block.level}"
            if block.kind == "heading"
            else "Bamboo Commentary" if block.kind == "commentary" else "Normal"
        )
        resolved = resolve_style(layout.book, block)
        if block.style:
            style = "Bamboo S " + block.style
        paragraph = doc.add_paragraph(style=style)
        format_paragraph(paragraph, resolved, p)
        paragraph.style.font.bold = resolved.bold
        if block.kind == "commentary" and previous is not None and not pending_break:
            previous.paragraph_format.keep_with_next = True
        paragraph.paragraph_format.page_break_before = pending_break
        pending_break = False
        paragraph.paragraph_format.keep_with_next = block.kind == "heading"
        paragraph.paragraph_format.first_line_indent = Pt(block.indent * p.cell_advance)
        paragraph.paragraph_format.widow_control = False
        pp = paragraph._element.get_or_add_pPr()
        pp.append(element("w:snapToGrid", val="0"))
        pp.append(element("w:autoSpaceDE", val="0"))
        pp.append(element("w:autoSpaceDN", val="0"))
        pp.append(element("w:kinsoku", val="1" if p.punctuation == "keep" else "0"))
        start = element("w:bookmarkStart", id=bi + 100, name=f"BambooBlock{bi}")
        paragraph._element.append(start)
        size = p.font_size * resolved.font_scale
        for ii, inline in enumerate(block.inlines):
            color = p.accent if inline.kind == "emphasis" else (resolved.ink or p.ink)
            if inline.kind == "note":
                note_id += 1
                _run(
                    paragraph,
                    inline.text,
                    font,
                    size,
                    color,
                    size + (p.cell_advance - size) / 2,
                    combine_id=note_id,
                )
            elif inline.kind == "footnote":
                footnotes.add(paragraph, inline.text)
            elif inline.kind == "ruby":
                _ruby(paragraph, inline, font, p, size)
            elif inline.kind == "numbered_note":
                numbered.reference(paragraph, inline)
            elif inline.kind == "seal":
                inline_seal(paragraph, inline, font, p, shape_id)
                shape_id += 1
            elif inline.kind == "label":
                boxed_label(
                    paragraph,
                    inline.text,
                    font,
                    size * 0.65,
                    color,
                    p.cell_advance,
                    inline.boxed,
                )
            else:
                relevant = [b for b in boxes if (b.block, b.inline) == (bi, ii)]
                offsets = sorted({b.offset for b in relevant})
                cursor = 0
                for offset in offsets:
                    if offset > cursor:
                        _text(
                            paragraph, inline.text[cursor:offset], font, p, size, color
                        )
                    for box in relevant:
                        if box.offset == offset:
                            _anchored_textbox(
                                paragraph, box, paragraph_glyphs[bi], font, p, shape_id
                            )
                            shape_id += 1
                    cursor = offset
                _text(paragraph, inline.text[cursor:], font, p, size, color)
        paragraph._element.append(element("w:bookmarkEnd", id=bi + 100))
        previous = paragraph
        numbered.flush()
    footnotes.finish()
    clean_styles(doc)
