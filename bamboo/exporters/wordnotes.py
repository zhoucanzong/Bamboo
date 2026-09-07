"""Native numbered annotation paragraphs, cross references and boxed labels."""

import hashlib
from docx.oxml.ns import qn
from .wordflow import element, set_font, _run


def bookmark_name(target):
    return "BambooNote_" + hashlib.sha256(target.encode()).hexdigest()[:24]


def boxed_label(paragraph, text, font, size, color, pitch, boxed=True):
    run = _run(paragraph, text, font, size, color, pitch)
    run._element.get_or_add_rPr().insert(0, element("w:rStyle", val="BambooLabel"))
    if boxed:
        run._element.get_or_add_rPr().append(
            element("w:bdr", val="single", sz=4, space=1, color=color[1:])
        )
    return run


class NumberedNotes:
    def __init__(self, doc, font, profile):
        self.doc, self.font, self.profile = doc, font, profile
        self.count = 0
        self.pending = []
        self.num_id = None

    def numbering(self):
        if self.num_id is not None:
            return self.num_id
        root = self.doc.part.numbering_part.element
        abstract_id = (
            max(
                [
                    int(n.get(qn("w:abstractNumId")))
                    for n in root.findall(qn("w:abstractNum"))
                ]
                + [-1]
            )
            + 1
        )
        num_id = (
            max([int(n.get(qn("w:numId"))) for n in root.findall(qn("w:num"))] + [0])
            + 1
        )
        abstract = element("w:abstractNum", abstractNumId=abstract_id)
        abstract.append(element("w:multiLevelType", val="singleLevel"))
        level = element("w:lvl", ilvl=0)
        for name, value in (
            ("start", 1),
            ("numFmt", "chineseCounting"),
            ("suff", "nothing"),
            ("lvlText", "【%1】"),
            ("lvlJc", "left"),
        ):
            level.append(element("w:" + name, val=value))
        pp = element("w:pPr")
        pp.append(element("w:ind", left=0, hanging=0))
        level.append(pp)
        props = element("w:rPr")
        set_font(props, self.font.family, self.profile.font_size * 0.65)
        props.append(element("w:snapToGrid", val="0"))
        props.append(
            element(
                "w:spacing",
                val=round(
                    (self.profile.cell_advance * 0.72 - self.profile.font_size * 0.65)
                    * 20
                ),
            )
        )
        level.append(props)
        abstract.append(level)
        first_num = root.find(qn("w:num"))
        root.insert(
            list(root).index(first_num) if first_num is not None else len(root),
            abstract,
        )
        num = element("w:num", numId=num_id)
        num.append(element("w:abstractNumId", val=abstract_id))
        root.append(num)
        self.num_id = num_id
        return num_id

    def reference(self, paragraph, inline):
        from ..layout import chinese_number

        self.count += 1

        def part(tag, value=None):
            run = element("w:r")
            rp = element("w:rPr")
            set_font(rp, self.font.family, self.profile.font_size * 0.6)
            run.append(rp)
            rp.append(element("w:snapToGrid", val="0"))
            rp.append(
                element(
                    "w:spacing",
                    val=round(
                        (
                            self.profile.cell_advance * 2 / 3
                            - self.profile.font_size * 0.6
                        )
                        * 20
                    ),
                )
            )
            if tag == "field":
                node = element("w:fldChar", fldCharType=value)
            else:
                node = element("w:" + tag)
                node.text = value
                node.set(qn("xml:space"), "preserve")
            run.append(node)
            paragraph._element.append(run)

        part("field", "begin")
        part("instrText", f" REF {bookmark_name(inline.target)} \\n \\h ")
        part("field", "separate")
        part("t", f"【{chinese_number(self.count)}】")
        part("field", "end")
        self.pending.append((inline, self.count))

    def flush(self):
        p = self.profile
        for inline, number in self.pending:
            paragraph = self.doc.add_paragraph(style="Bamboo Numbered Note")
            props = paragraph._element.get_or_add_pPr()
            props.append(element("w:snapToGrid", val="0"))
            num = element("w:numPr")
            num.append(element("w:ilvl", val=0))
            num.append(element("w:numId", val=self.numbering()))
            props.append(num)
            paragraph._element.append(
                element(
                    "w:bookmarkStart",
                    id=100000 + number,
                    name=bookmark_name(inline.target),
                )
            )
            padding = _run(
                paragraph, " ", self.font, p.font_size * 0.65, p.ink, p.font_size * 0.65
            )
            padding._element.get_or_add_rPr().insert(
                0, element("w:rStyle", val="BambooNotePadding")
            )
            if inline.annotation:
                boxed_label(
                    paragraph,
                    inline.annotation,
                    self.font,
                    p.font_size * 0.65,
                    p.ink,
                    p.cell_advance * 0.72,
                    inline.boxed,
                )
            _run(
                paragraph,
                inline.text,
                self.font,
                p.font_size * 0.65,
                p.ink,
                p.cell_advance * 0.72,
            )
            paragraph._element.append(element("w:bookmarkEnd", id=100000 + number))
        self.pending = []
