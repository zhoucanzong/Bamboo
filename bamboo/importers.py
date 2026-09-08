"""Import adapters into editable documents. Live DOCX text wins over snapshots."""

from dataclasses import replace
from io import BytesIO
import json
import re
import zipfile

from docx import Document
from docx.oxml.ns import qn
from lxml import etree

from .editor import EditorSession
from .model import BambooError, Block, Book, Inline, PRESETS, Profile


def import_plain_text(text, title="未命名文档", profile=None):
    """Plain text is text; no markup syntax is interpreted."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = tuple(Block((Inline(line),) if line else ()) for line in text.split("\n"))
    return EditorSession(
        Book(
            title or "未命名文档",
            blocks,
            volume="",
            profile=profile or PRESETS["single"].updated(punctuation="keep"),
        )
    )


def import_docx(data):
    warnings = []
    saved_profile = None
    saved_book = None
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            if sum(i.file_size for i in archive.infolist()) > 100_000_000:
                raise BambooError("文档解压后超过 100MB")
            parser = etree.XMLParser(resolve_entities=False, no_network=True)
            if "customXml/bamboo-source.xml" in archive.namelist():
                try:
                    snapshot = json.loads(
                        etree.fromstring(
                            archive.read("customXml/bamboo-source.xml"), parser
                        ).text
                    )
                    saved_profile = Profile(**snapshot["profile"])
                    from .parser import from_dict

                    saved_book = from_dict(snapshot)
                except (ValueError, TypeError, KeyError, BambooError):
                    pass
            notes = {}
            if "word/footnotes.xml" in archive.namelist():
                root = etree.fromstring(archive.read("word/footnotes.xml"), parser)
                for note in root:
                    if note.get(qn("w:type")):
                        continue
                    notes[note.get(qn("w:id"))] = "".join(note.itertext()).strip()
                    notes[note.get(qn("w:id"))] = "".join(
                        t.text or "" for t in note.iter(qn("w:t"))
                    )
            if any(name.startswith("word/media/") for name in archive.namelist()):
                warnings.append("已导入可编辑文字；图片与装饰没有转成可编辑对象。")
        doc = Document(BytesIO(data))
    except BambooError:
        raise
    except Exception as e:
        raise BambooError(f"无法打开 Word 文档: {e}") from e

    section = doc.sections[0]
    direction = section._sectPr.find(qn("w:textDirection"))
    vertical = direction is not None and direction.get(qn("w:val")) in {"tbRl", "tbRlV"}
    preset = PRESETS["single" if vertical else "horizontal"]
    # Preserve the paper and direction. Imported layout is an editable grid,
    # rather than an assertion that all third-party Word formatting is supported.
    width, height = section.page_width.pt, section.page_height.pt
    size = min(18, preset.font_size)
    profile = preset.updated(
        width=width,
        height=height,
        margin_x=max(24, min(section.left_margin.pt, width / 5)),
        margin_top=max(24, min(section.top_margin.pt, height / 5)),
        margin_bottom=max(24, min(section.bottom_margin.pt, height / 5)),
        spine=0,
        rules=False,
        border="none",
        font_size=min(size, 12),
        punctuation="keep",
    )
    if saved_profile:
        try:
            profile = saved_profile.updated(
                width=width,
                height=height,
                writing_mode="vertical-rl" if vertical else "horizontal-tb",
            )
        except BambooError:
            warnings.append("原版式与当前 Word 页面尺寸不匹配，已采用可编辑网格。")
    blocks = []
    floating = []
    numbered_entries = {}
    used_entries = set()
    for para in doc._element.body.findall(qn("w:p")):
        style = para.find(qn("w:pPr"))
        style = style.find(qn("w:pStyle")) if style is not None else None
        if style is None or style.get(qn("w:val")) != "BambooNumberedNote":
            continue
        bookmark = next(
            (
                n.get(qn("w:name"))
                for n in para.findall(qn("w:bookmarkStart"))
                if (n.get(qn("w:name")) or "").startswith("BambooNote_")
            ),
            None,
        )
        if not bookmark:
            continue
        labels = []
        content = []
        boxed = True
        for run in para.findall(qn("w:r")):
            value = "".join(t.text or "" for t in run.iter(qn("w:t")))
            rp = run.find(qn("w:rPr"))
            rs = rp.find(qn("w:rStyle")) if rp is not None else None
            style_name = rs.get(qn("w:val")) if rs is not None else ""
            if style_name == "BambooNotePadding":
                continue
            if rp is not None and (
                rp.find(qn("w:bdr")) is not None or style_name == "BambooLabel"
            ):
                labels.append(value)
                boxed = rp.find(qn("w:bdr")) is not None
            else:
                content.append(value)
        numbered_entries[bookmark] = ("".join(content), "".join(labels), boxed)

    def read_run(run):
        rp = run.find(qn("w:rPr"))
        kind = "text"
        boxed = True
        if rp is not None:
            combine = rp.find(qn("w:eastAsianLayout"))
            color = rp.find(qn("w:color"))
            rs = rp.find(qn("w:rStyle"))
            if combine is not None and combine.get(qn("w:combine")) in {
                "1",
                "true",
                "on",
            }:
                kind = "note"
            elif rp.find(qn("w:bdr")) is not None or (
                rs is not None and rs.get(qn("w:val")) == "BambooLabel"
            ):
                kind = "label"
                boxed = rp.find(qn("w:bdr")) is not None
            elif color is not None and color.get(qn("w:val"), "").lower() in {
                "9b3028",
                "ff0000",
                "aa4539",
            }:
                kind = "emphasis"
        spans, buffer = [], []

        def flush():
            if buffer:
                spans.append(Inline("".join(buffer), kind, boxed=boxed))
                buffer.clear()

        for child in run:
            if child.tag == qn("w:t"):
                buffer.append(child.text or "")
            elif child.tag == qn("w:tab"):
                buffer.append("　")
            elif child.tag == qn("w:br"):
                buffer.append("\n")
            elif child.tag == qn("w:ruby"):
                flush()
                base = child.find(qn("w:rubyBase"))
                rt = child.find(qn("w:rt"))
                text = (
                    "".join(t.text or "" for t in base.iter(qn("w:t")))
                    if base is not None
                    else ""
                )
                note = (
                    "".join(t.text or "" for t in rt.iter(qn("w:t")))
                    if rt is not None
                    else ""
                )
                if text:
                    if note and len(text) <= 8 and len(note) <= 16:
                        spans.append(Inline(text, "ruby", note))
                    else:
                        spans.append(Inline(text))
                        if note:
                            spans.append(Inline(note, "note"))
                            warnings.append("过长的 Word 旁注已作为夹注保留。")
            elif child.tag == qn("w:footnoteReference"):
                flush()
                text = notes.get(child.get(qn("w:id")), "")
                if text:
                    spans.append(Inline(text, "footnote"))
            elif child.tag in {qn("w:pict"), qn("w:drawing")}:
                seal = next(
                    (
                        shape
                        for shape in child.iter()
                        if (shape.get("id") or "").startswith("BambooSeal")
                    ),
                    None,
                )
                if seal is not None:
                    flush()
                    text = "".join(t.text or "" for t in seal.iter(qn("w:t")))
                    if text:
                        try:
                            spans.append(
                                Inline(
                                    text,
                                    "seal",
                                    seal_style=(
                                        "white" if seal.get("filled") == "t" else "red"
                                    ),
                                )
                            )
                        except BambooError:
                            spans.append(Inline(text))
                            warnings.append("印文超出方印容量，已保留为普通文字。")
                    continue
                for box in child.iter(qn("w:txbxContent")):
                    text = "".join(t.text or "" for t in box.iter(qn("w:t")))
                    if text:
                        floating.append(text)
        flush()
        return spans

    def read_field(instruction, runs):
        match = re.search(r"\bREF\s+(BambooNote_[A-Za-z0-9_]+)", instruction)
        if match and match.group(1) in numbered_entries:
            target = match.group(1)
            text, label, boxed = numbered_entries[target]
            if target not in used_entries and text:
                used_entries.add(target)
                return [Inline(text, "numbered_note", label, target, boxed)]
        return [span for run in runs for span in read_run(run)]

    from .model import SectionSpec
    from .styles import context_at, style_registry

    native_sections = list(doc.sections)
    section_index = 0
    used_sections = set()
    registry = style_registry(saved_book) if saved_book else {}
    native_styles = {
        s.style_id: s.name[9:] for s in doc.styles if s.name.startswith("Bamboo S ")
    }

    def original_index(element):
        for b in element.iter(qn("w:bookmarkStart")):
            name = b.get(qn("w:name"), "")
            if re.fullmatch(r"BambooBlock\d+", name):
                return int(name[11:])
        return None

    def adapted(block, index, si, cover=False):
        # Source metadata supplies style definitions only; all text above is live OOXML.
        source = (
            saved_book.blocks[index]
            if saved_book and index is not None and index < len(saved_book.blocks)
            else None
        )
        if source:
            block = replace(
                block,
                style=source.style if source.style in registry else "",
                indent=source.indent,
                level=source.level,
            )
        if si not in used_sections:
            used_sections.add(si)
            if len(native_sections) > 1 or (source and source.section):
                spec = (
                    context_at(saved_book, index)
                    if source
                    else SectionSpec(profile=profile)
                )
                native = native_sections[si]
                direction = native._sectPr.find(qn("w:textDirection"))
                mode = (
                    "vertical-rl"
                    if direction is not None
                    and direction.get(qn("w:val")) in {"tbRl", "tbRlV"}
                    else "horizontal-tb"
                )
                try:
                    active = spec.profile.updated(
                        width=native.page_width.pt,
                        height=native.page_height.pt,
                        writing_mode=mode,
                    )
                except BambooError:
                    active = profile
                spec = replace(
                    spec, profile=active, page_type="title-slip" if cover else "body"
                )
                block = replace(block, section=spec)
        return block

    for element in doc._element.body:
        if element.tag == qn("w:tbl"):
            warnings.append("表格文字已按行导入；表格几何结构暂未导入。")
            for row in element.findall(qn("w:tr")):
                cells = [
                    "".join(t.text or "" for t in cell.iter(qn("w:t")))
                    for cell in row.findall(qn("w:tc"))
                ]
                text = "　".join(cells)
                blocks.append(Block((Inline(text),) if text else ()))
            continue
        if element.tag != qn("w:p"):
            if element.tag != qn("w:sectPr"):
                warnings.append("部分结构化控件尚未导入，请核对原文件。")
            continue
        pp = element.find(qn("w:pPr"))
        si = section_index
        ends_section = pp is not None and pp.find(qn("w:sectPr")) is not None
        if ends_section:
            section_index = min(section_index + 1, len(native_sections) - 1)
        cover = next(
            (
                shape
                for shape in element.iter()
                if re.fullmatch(r"BambooCover\d+", shape.get("id") or "")
            ),
            None,
        )
        if cover is not None:
            for pe in cover.iter(qn("w:p")):
                active = None
                cover_spans = []
                for node in pe:
                    if node.tag == qn("w:bookmarkStart") and re.fullmatch(
                        r"BambooBlock\d+", node.get(qn("w:name"), "")
                    ):
                        active = int(node.get(qn("w:name"))[11:])
                        cover_spans = []
                    elif node.tag == qn("w:r") and active is not None:
                        cover_spans.extend(read_run(node))
                    elif node.tag == qn("w:bookmarkEnd") and active is not None:
                        kind = "heading" if not blocks else "paragraph"
                        blocks.append(
                            adapted(Block(tuple(cover_spans), kind), active, si, True)
                        )
                        active = None
            if not any(t.text for t in cover.iter(qn("w:t"))):
                blocks.append(adapted(Block(), None, si, True))
            elif not blocks:
                text = "".join(t.text or "" for t in cover.iter(qn("w:t")))
                blocks.append(
                    adapted(Block((Inline(text),), "heading"), None, si, True)
                )
            continue
        if ends_section and not any(t.text for t in element.iter(qn("w:t"))):
            continue
        kind, level, style_key = "paragraph", 1, ""
        if pp is not None:
            style = pp.find(qn("w:pStyle"))
            name = style.get(qn("w:val"), "") if style is not None else ""
            if name == "BambooNumberedNote" and any(
                n.get(qn("w:name")) in numbered_entries
                for n in element.findall(qn("w:bookmarkStart"))
            ):
                continue
            if name in native_styles and native_styles[name] in registry:
                style_key = native_styles[name]
                kind = registry[style_key].role
            if name.lower().startswith("heading") and name[-1:].isdigit():
                kind, level = "heading", max(1, int(name[-1]))
            elif name == "BambooCommentary":
                kind = "commentary"
            breaking = pp.find(qn("w:pageBreakBefore"))
            if (
                breaking is not None
                and breaking.get(qn("w:val")) not in {"0", "false", "off"}
                and blocks
            ):
                blocks.append(Block(kind="pagebreak"))
        spans = []
        field_runs = []
        field_depth = 0
        for child in element:
            if child.tag == qn("w:r"):
                controls = [
                    n.get(qn("w:fldCharType")) for n in child.findall(qn("w:fldChar"))
                ]
                if field_depth or "begin" in controls:
                    field_runs.append(child)
                    field_depth += controls.count("begin") - controls.count("end")
                    if field_depth == 0:
                        instruction = "".join(
                            n.text or ""
                            for r in field_runs
                            for n in r.findall(qn("w:instrText"))
                        )
                        spans.extend(
                            read_field(
                                instruction,
                                [
                                    r
                                    for r in field_runs
                                    if r.find(qn("w:t")) is not None
                                ],
                            )
                        )
                        field_runs = []
                    continue
                spans.extend(read_run(child))
            elif child.tag in {qn("w:hyperlink"), qn("w:ins")}:
                for run in child.iter(qn("w:r")):
                    spans.extend(read_run(run))
            elif child.tag == qn("w:fldSimple"):
                spans.extend(
                    read_field(
                        child.get(qn("w:instr"), ""), list(child.iter(qn("w:r")))
                    )
                )
        if field_runs:
            spans.extend(span for run in field_runs for span in read_run(run))
        blocks.append(
            adapted(
                Block(tuple(spans), kind, level=level, style=style_key),
                original_index(element),
                si,
            )
        )
        for text in floating:
            blocks.append(Block((Inline(text),), "commentary"))
        if floating:
            warnings.append("浮动批注文字已作为随段课注保留，其原始位置暂未恢复。")
            floating.clear()
    book = Book(
        doc.core_properties.title or "导入的文档",
        tuple(blocks or [Block()]),
        author=doc.core_properties.author or "",
        volume="",
        profile=profile,
        styles=saved_book.styles if saved_book else (),
    )
    remaining = [
        (
            Block(
                (Inline(label, "label", boxed=boxed), Inline(text)), kind="commentary"
            )
            if label
            else Block((Inline(text),), kind="commentary")
        )
        for target, (text, label, boxed) in numbered_entries.items()
        if target not in used_entries and text
    ]
    if remaining:
        book = replace(book, blocks=book.blocks + tuple(remaining))
        warnings.append("未能恢复的编号关联已按课注保留文字，请核对引用。")
    return EditorSession(book), list(dict.fromkeys(warnings))


def import_document(data, filename):
    if filename.lower().endswith(".docx"):
        return import_docx(data)
    if filename.lower().endswith(".json"):
        try:
            parsed = json.loads(data.decode("utf-8-sig"))
            if isinstance(parsed, dict) and "editor_schema" in parsed:
                return EditorSession.restore(parsed), []
            from .parser import from_dict

            return EditorSession(from_dict(parsed)), []
        except (ValueError, KeyError, TypeError) as e:
            raise BambooError(f"无法恢复编辑文档: {e}") from e
    try:
        return (
            import_plain_text(data.decode("utf-8-sig"), filename.rsplit(".", 1)[0]),
            [],
        )
    except UnicodeError as e:
        raise BambooError("文本文件需要 UTF-8 编码") from e
