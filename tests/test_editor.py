from dataclasses import asdict, replace
from io import BytesIO
import json
import zipfile

from docx import Document
import pytest

from bamboo import (
    Annotation,
    Block,
    Book,
    EditorSession,
    Inline,
    Position,
    PRESETS,
    RevisionConflict,
)
from bamboo.importers import import_docx, import_plain_text
from bamboo.model import BambooError


def selected(session, start, end, block=0):
    return {
        "anchor": {"block_id": session.block_ids[block], "offset": start},
        "focus": {"block_id": session.block_ids[block], "offset": end},
    }


def test_blank_document_accepts_input_without_files():
    s = EditorSession()
    assert not s.book.blocks[0].text
    assert len(s.layout().pages) == 1
    s.dispatch({"type": "insert_text", "text": "天地玄黃"})
    assert s.book.blocks[0].text == "天地玄黃"
    assert s.selection.focus.offset == 4
    assert s.layout().book == s.book


def test_atomic_command_group_and_single_undo():
    s = EditorSession()
    s.dispatch(
        [{"type": "insert_text", "text": "甲"}, {"type": "insert_text", "text": "乙"}]
    )
    assert s.revision == 1 and s.book.blocks[0].text == "甲乙"
    s.dispatch({"type": "undo"})
    assert not s.book.blocks[0].text and s.revision == 2
    s.dispatch({"type": "redo"})
    assert s.book.blocks[0].text == "甲乙" and s.revision == 3


def test_failed_transaction_keeps_document_history_and_selection():
    s = EditorSession()
    before = s.state()
    with pytest.raises(BambooError):
        s.dispatch(
            [
                {"type": "insert_text", "text": "不得丟失"},
                {"type": "set_profile", "values": {"font_size": 999}},
            ]
        )
    assert s.state() == before


def test_revision_conflict_prevents_lost_update():
    s = EditorSession()
    s.dispatch({"type": "insert_text", "text": "甲"}, expected_revision=0)
    with pytest.raises(RevisionConflict):
        s.dispatch({"type": "insert_text", "text": "乙"}, expected_revision=0)
    assert s.book.blocks[0].text == "甲"


def test_new_edit_after_undo_clears_redo():
    s = import_plain_text("甲")
    s.dispatch({"type": "insert_text", "text": "乙"})
    s.dispatch({"type": "undo"})
    s.dispatch({"type": "insert_text", "text": "丙"})
    assert not s.state()["can_redo"]


def test_split_and_merge_preserve_first_paragraph_identity():
    s = import_plain_text("天地玄黃")
    original = s.block_ids[0]
    s.select(Position(original, 2))
    s.dispatch({"type": "split_paragraph"})
    assert [b.text for b in s.book.blocks] == ["天地", "玄黃"]
    assert s.block_ids[0] == original and s.block_ids[1] != original
    s.dispatch({"type": "delete_backward"})
    assert [b.text for b in s.book.blocks] == ["天地玄黃"]
    assert s.block_ids == (original,)


def test_multiblock_selection_replacement_and_undo():
    s = import_plain_text("天地\n玄黃\n宇宙")
    selection = {
        "anchor": {"block_id": s.block_ids[0], "offset": 1},
        "focus": {"block_id": s.block_ids[2], "offset": 1},
    }
    s.dispatch({"type": "replace_range", "text": "新\n文", "selection": selection})
    assert [b.text for b in s.book.blocks] == ["天新", "文宙"]
    s.dispatch({"type": "undo"})
    assert [b.text for b in s.book.blocks] == ["天地", "玄黃", "宇宙"]


def test_note_content_can_be_edited_in_place():
    s = EditorSession(
        Book("注", (Block((Inline("甲"), Inline("天地", "note"), Inline("乙"))),))
    )
    s.select(Position(s.block_ids[0], 2))
    s.dispatch({"type": "insert_text", "text": "玄"})
    assert [(i.kind, i.text) for i in s.book.blocks[0].inlines] == [
        ("text", "甲"),
        ("note", "天玄地"),
        ("text", "乙"),
    ]


def test_format_selection_as_double_note_then_plain():
    s = import_plain_text("天地玄黃")
    s.dispatch({"type": "format_range", "kind": "note", "selection": selected(s, 1, 3)})
    assert [(i.kind, i.text) for i in s.book.blocks[0].inlines] == [
        ("text", "天"),
        ("note", "地玄"),
        ("text", "黃"),
    ]
    s.dispatch({"type": "format_range", "kind": "text", "selection": selected(s, 1, 3)})
    assert s.book.blocks[0].inlines == (Inline("天地玄黃"),)


def test_ruby_edits_preserve_annotation_and_refuse_partial_split():
    s = EditorSession(Book("旁", (Block((Inline("天地", "ruby", "萬物"),)),)))
    s.select(Position(s.block_ids[0], 1))
    s.dispatch({"type": "insert_text", "text": "人"})
    assert s.book.blocks[0].inlines[0] == Inline("天人地", "ruby", "萬物")
    before = s.state()
    with pytest.raises(BambooError, match="拆开"):
        s.dispatch({"type": "split_paragraph"})
    assert s.state() == before


def test_annotation_anchor_tracks_insert_split_merge_and_undo():
    s = EditorSession(
        Book(
            "批",
            (Block((Inline("天地玄黃"),)),),
            annotations=(Annotation("注", 0, offset=2),),
        )
    )
    s.dispatch({"type": "insert_text", "text": "甲"})
    assert s.book.annotations[0].offset == 3
    s.select(Position(s.block_ids[0], 2))
    s.dispatch({"type": "split_paragraph"})
    assert s.book.annotations[0].block == 1 and s.book.annotations[0].offset == 1
    s.dispatch({"type": "delete_backward"})
    assert s.book.annotations[0].block == 0 and s.book.annotations[0].offset == 3
    s.dispatch({"type": "undo"})
    assert s.book.annotations[0].block == 1


def test_deleting_anchor_and_note_is_undoable():
    s = EditorSession(
        Book("批", (Block((Inline("天地"),)),), annotations=(Annotation("注", 0),))
    )
    s.dispatch({"type": "replace_range", "text": "", "selection": selected(s, 0, 1)})
    assert not s.book.annotations
    s.dispatch({"type": "undo"})
    assert s.book.annotations[0].text == "注"


def test_annotation_indices_update_when_styles_split_spans():
    s = EditorSession(
        Book(
            "批",
            (Block((Inline("天地玄黃"),)),),
            annotations=(Annotation("注", 0, offset=3),),
        )
    )
    s.dispatch(
        {"type": "format_range", "kind": "emphasis", "selection": selected(s, 0, 2)}
    )
    n = s.book.annotations[0]
    assert n.inline == 1 and n.offset == 1


def test_deletion_uses_cluster_boundary_and_extended_unicode():
    s = import_plain_text("甲\U00020000\U000e0100乙")
    s.select(Position(s.block_ids[0], 3))
    s.dispatch({"type": "delete_backward"})
    assert s.book.blocks[0].text == "甲乙"
    with pytest.raises(BambooError):
        s.select(Position(s.block_ids[0], 99))


def test_editing_all_text_away_leaves_real_blank_paragraph():
    s = import_plain_text("天地")
    s.dispatch({"type": "replace_range", "selection": selected(s, 0, 2), "text": ""})
    assert s.book.blocks == (Block(),)
    assert len(s.layout().pages) == 1
    assert s.caret()["page"] == 0


def test_layout_is_cached_and_invalid_annotation_does_not_discard_input():
    s = import_plain_text("天地")
    first = s.layout()
    assert s.layout() is first
    s.dispatch(
        {"type": "add_annotation", "placement": "top", "text": "注" * 20, "extent": 20}
    )
    s.layout()
    assert s.issues and s.book.annotations[0].text == "注" * 20
    s.dispatch({"type": "remove_annotation", "index": 0})
    s.layout()
    assert not s.issues


@pytest.mark.parametrize("preset", ["single", "horizontal"])
def test_hit_test_and_caret_geometry(preset):
    s = EditorSession(
        Book("游標", (Block((Inline("天地"),)),), profile=PRESETS[preset])
    )
    glyph = next(g for g in s.layout().pages[0].glyphs if g.block == 0)
    p = s.hit_test(0, glyph.x + glyph.width * 0.1, glyph.y + glyph.height * 0.1)
    assert p == Position(s.block_ids[0], 0)
    caret = s.caret(p)
    assert (caret["y1"] == caret["y2"]) == s.book.profile.vertical


def test_save_restore_preserves_identifiers_and_special_formats(tmp_path):
    s = import_plain_text("天地")
    s.dispatch({"type": "format_range", "kind": "note", "selection": selected(s, 0, 2)})
    path = tmp_path / "document.json"
    s.save(path)
    restored = EditorSession.restore(json.loads(path.read_text()))
    assert restored.book == s.book and restored.block_ids == s.block_ids
    assert restored.selection == s.selection and restored.revision == s.revision


def test_plain_text_import_does_not_parse_markup():
    s = import_plain_text("@title 這就是正文\n[[這也只是正文]]")
    assert s.book.blocks[0].text == "@title 這就是正文"
    assert s.book.blocks[1].inlines[0].kind == "text"


def test_docx_import_reads_actual_content_not_old_embedded_snapshot():
    d = Document()
    d.add_paragraph("這是修改後的正文")
    data = BytesIO()
    d.save(data)
    # Even a misleading custom source snapshot must not replace the live story.
    output = BytesIO()
    with (
        zipfile.ZipFile(BytesIO(data.getvalue())) as original,
        zipfile.ZipFile(output, "w") as target,
    ):
        for info in original.infolist():
            target.writestr(info, original.read(info.filename))
        target.writestr(
            "customXml/bamboo-source.xml",
            '<source>{"title":"過期","blocks":[{"text":"不應讀取"}]}</source>',
        )
    s, warnings = import_docx(output.getvalue())
    assert s.book.blocks[0].text == "這是修改後的正文"


def test_import_export_native_word_notes_roundtrip(tmp_path):
    from bamboo import render

    s = EditorSession(
        Book(
            "回讀",
            (Block((Inline("正文"), Inline("小注", "note"), Inline("課文"))),),
            profile=PRESETS["single"],
        )
    )
    result = render(s.book, tmp_path, formats=["docx"])
    restored, warnings = import_docx(open(result.files["docx"], "rb").read())
    assert restored.book.profile.vertical
    assert restored.book.profile.columns == s.book.profile.columns
    assert restored.book.profile.font_size == s.book.profile.font_size
    assert "".join(b.text for b in restored.book.blocks) == "正文小注課文"
    assert any(i.kind == "note" for b in restored.book.blocks for i in b.inlines)
