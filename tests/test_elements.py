from dataclasses import replace
from pathlib import Path
import zipfile

from lxml import etree
import pytest

from bamboo import (
    Block,
    Book,
    EditorSession,
    Inline,
    Position,
    PRESETS,
    compose,
    render,
)
from bamboo.importers import import_docx
from bamboo.symbols import STYLES, DIRECTIONS, fish_tail


def test_new_document_has_no_template_decorations():
    s = EditorSession()
    page = s.layout().pages[0]
    assert not page.lines and not page.polygons and not page.glyphs
    assert s.book.profile.spine == 0 and s.book.profile.paper == "#ffffff"


def test_elements_toggle_independently_and_are_undoable():
    s = EditorSession()
    s.dispatch({"type": "insert_text", "text": "天地"})
    s.dispatch({"type": "set_profile", "values": {"spine": 32, "fish_tail": True}})
    p = s.layout().pages[0]
    assert p.polygons and not p.lines
    assert all(g.block >= 0 for g in p.glyphs)
    s.dispatch(
        {"type": "set_profile", "values": {"fish_tail": False, "border": "single"}}
    )
    p = s.layout().pages[0]
    assert not p.polygons and len(p.lines) == 4
    s.dispatch({"type": "undo"})
    assert s.layout().pages[0].polygons and not s.layout().pages[0].lines


def test_direction_does_not_reapply_a_template():
    s = EditorSession()
    original = s.book.profile
    s.dispatch({"type": "set_direction", "writing_mode": "horizontal-tb"})
    p = s.book.profile
    assert not p.vertical and p.width == original.width and p.height == original.height
    assert (
        p.font_size == original.font_size
        and p.spine == 0
        and not p.fish_tail
        and p.border == "none"
    )
    s.dispatch({"type": "set_direction", "writing_mode": "vertical-rl"})
    assert not s.layout().pages[0].polygons


@pytest.mark.parametrize(
    "flag,text",
    [("show_title", "測試"), ("show_volume", "卷一"), ("show_page_number", "一")],
)
def test_spine_text_is_optional(flag, text):
    p = PRESETS["blank"].updated(spine=32, **{flag: True})
    layout = compose(Book("測試", (Block(),), profile=p))
    assert "".join(g.text for g in layout.pages[0].glyphs) == text


@pytest.mark.parametrize("style", list(STYLES))
@pytest.mark.parametrize("direction", list(DIRECTIONS))
def test_vector_symbols_are_font_independent_and_bounded(style, direction):
    lines, polygons = fish_tail(style, direction, 30, 30, 24, "#cc0000")
    assert lines or polygons
    points = (
        [point for p in polygons for point in p.points]
        + [(l.x1, l.y1) for l in lines]
        + [(l.x2, l.y2) for l in lines]
    )
    assert all(17 <= x <= 43 and 17 <= y <= 43 for x, y in points)


def test_numbered_notes_preserve_selection_and_renumber_after_deletion():
    s = EditorSession()
    s.dispatch({"type": "insert_text", "text": "天地玄黃"})
    s.select(Position(s.block_ids[0], 0), Position(s.block_ids[0], 2))
    s.dispatch(
        {"type": "add_numbered_note", "text": "第一條注文", "annotation": "集解"}
    )
    first = next(i for i in s.book.blocks[0].inlines if i.kind == "numbered_note")
    assert s.book.blocks[0].inlines[0].text == "天地"
    s.select(Position(s.block_ids[0], 0))
    s.dispatch(
        {"type": "add_numbered_note", "text": "後加但先引用", "annotation": "索隱"}
    )
    notes = [i for i in s.book.blocks[0].inlines if i.kind == "numbered_note"]
    markers = [
        g for p in s.layout().pages for g in p.glyphs if g.role == "note_reference"
    ]
    assert "一" in "".join(g.text for g in markers if g.reference_id == notes[0].target)
    assert "二" in "".join(g.text for g in markers if g.reference_id == first.target)
    s.dispatch({"type": "remove_numbered_note", "target": notes[0].target})
    markers = [
        g.text for p in s.layout().pages for g in p.glyphs if g.role == "note_reference"
    ]
    assert "一" in markers and "二" not in markers
    s.dispatch({"type": "undo"})
    assert (
        len([i for b in s.book.blocks for i in b.inlines if i.kind == "numbered_note"])
        == 2
    )


def test_update_note_keeps_identity_and_label_can_lose_its_box():
    s = EditorSession()
    s.dispatch({"type": "add_numbered_note", "text": "原注", "annotation": "集解"})
    target = s.book.blocks[0].inlines[0].target
    s.dispatch(
        {
            "type": "update_numbered_note",
            "target": target,
            "text": "修訂注文",
            "annotation": "索隱",
            "boxed": False,
        }
    )
    n = s.book.blocks[0].inlines[0]
    assert n.target == target and n.text == "修訂注文" and not n.boxed
    assert not s.layout().pages[0].lines


@pytest.mark.parametrize("boxed", [True, False])
def test_label_export_and_native_word_roundtrip(tmp_path, boxed):
    b = Book(
        "標籤",
        (Block((Inline("集解", "label", boxed=boxed), Inline("正文"))),),
        profile=PRESETS["blank"],
    )
    out = render(b, tmp_path, formats=["pdf", "html", "docx"])
    imported, _ = import_docx(Path(out.files["docx"]).read_bytes())
    label = next(
        i for block in imported.book.blocks for i in block.inlines if i.kind == "label"
    )
    assert label.text == "集解" and label.boxed == boxed
    assert bool(compose(b).pages[0].lines) == boxed


def test_numbered_word_has_real_fields_numbering_and_roundtrip(tmp_path):
    s = EditorSession()
    s.dispatch({"type": "insert_text", "text": "天地"})
    s.dispatch(
        {
            "type": "add_numbered_note",
            "text": "注文內容",
            "annotation": "集解",
            "boxed": False,
        }
    )
    out = render(s.book, tmp_path)
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(out.files["docx"]) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        assert "REF BambooNote_" in "".join(
            root.xpath("//w:instrText/text()", namespaces=ns)
        )
        assert root.xpath(
            '//w:bookmarkStart[starts-with(@w:name,"BambooNote_")]', namespaces=ns
        )
        assert root.xpath("//w:numPr", namespaces=ns)
        numbering = etree.fromstring(z.read("word/numbering.xml"))
        assert numbering.xpath('//w:numFmt[@w:val="chineseCounting"]', namespaces=ns)
        kinds = [etree.QName(e).localname for e in numbering]
        assert max(i for i, k in enumerate(kinds) if k == "abstractNum") < min(
            i for i, k in enumerate(kinds) if k == "num"
        )
    imported, _ = import_docx(Path(out.files["docx"]).read_bytes())
    note = next(
        i for b in imported.book.blocks for i in b.inlines if i.kind == "numbered_note"
    )
    assert note.text == "注文內容" and note.annotation == "集解" and not note.boxed
    assert 'href="#note-' in Path(out.files["html"]).read_text()


def test_disabled_decorations_do_not_create_word_header(tmp_path):
    out = render(EditorSession().book, tmp_path, formats=["docx"])
    with zipfile.ZipFile(out.files["docx"]) as z:
        assert not any(name.startswith("word/header") for name in z.namelist())
        assert not any(name.startswith("word/media/") for name in z.namelist())


def test_tight_grid_keeps_label_input_and_returns_layout_issue():
    s = EditorSession(
        Book(
            "標籤",
            (Block((Inline("注家名", "label"),)),),
            profile=PRESETS["blank"].updated(rows=2),
        )
    )
    assert s.layout().pages and s.issues
    assert s.book.blocks[0].inlines[0].kind == "label"
