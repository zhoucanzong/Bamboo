from dataclasses import replace
from pathlib import Path
import json
import zipfile

from lxml import etree
import pytest

from bamboo import (
    Annotation,
    BambooError,
    Block,
    Book,
    Inline,
    PRESETS,
    compose,
    from_dict,
    load,
    parse,
    render,
)

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}
ROOT = Path(__file__).resolve().parents[1]


def xml(result, member="word/document.xml"):
    with zipfile.ZipFile(result.files["docx"]) as z:
        return etree.fromstring(z.read(member))


@pytest.mark.parametrize(
    "preset,direction", [("single", "tbRl"), ("horizontal", "lrTb")]
)
def test_default_docx_is_direction_preserving_continuous_text(
    tmp_path, preset, direction
):
    b = parse(f"@preset {preset}\n@title 流式測試\n" + "天地玄黃宇宙洪荒" * 200)
    result = render(b, tmp_path, formats=["docx"])
    root = xml(result)
    assert root.xpath("//w:textDirection/@w:val", namespaces=NS) == [direction]
    assert len(root.xpath("//w:body/w:p", namespaces=NS)) == 1
    assert not root.xpath(
        "//w:body//w:drawing | //w:body//w:txbxContent | //w:br", namespaces=NS
    )
    assert not root.xpath(
        "//w:pageBreakBefore[not(@w:val) or @w:val='1']", namespaces=NS
    )
    assert (
        "".join(root.xpath("//w:body//w:t/text()", namespaces=NS)) == b.blocks[0].text
    )
    assert json.loads(Path(result.files["manifest"]).read_text())["docx_mode"] == "flow"


def test_commentary_is_a_following_native_paragraph(tmp_path):
    b = parse("@title 段后注\n正文講述一件事。\n\n> 段后注說明其義。\n\n後文仍可續排。")
    root = xml(render(b, tmp_path, formats=["docx"]))
    paras = root.xpath("//w:body/w:p", namespaces=NS)
    assert paras[0].find("w:pPr/w:keepNext", NS) is not None
    assert paras[1].xpath("w:pPr/w:pStyle/@w:val", namespaces=NS) == [
        "BambooCommentary"
    ]
    assert "段后注說明其義" in "".join(paras[1].xpath(".//w:t/text()", namespaces=NS))


def test_footnotes_are_native_relationships_and_references(tmp_path):
    b = parse("@preset horizontal\n正文((第一條腳注))。另文((第二條脚注))。")
    result = render(b, tmp_path, formats=["docx"])
    root = xml(result)
    assert root.xpath("//w:footnoteReference/@w:id", namespaces=NS) == ["1", "2"]
    notes = xml(result, "word/footnotes.xml")
    assert notes.xpath("//w:footnote/@w:id", namespaces=NS) == ["-1", "0", "1", "2"]
    assert "第一條腳注" in "".join(notes.xpath("//w:t/text()", namespaces=NS))
    with zipfile.ZipFile(result.files["docx"]) as z:
        assert (
            "relationships/footnotes" in z.read("word/_rels/document.xml.rels").decode()
        )


def test_short_ruby_is_a_native_run_child(tmp_path):
    b = from_dict(
        {
            "title": "旁注",
            "preset": "single",
            "blocks": [
                {
                    "inlines": [
                        {"text": "學而時習之", "kind": "ruby", "annotation": "溫故知新"}
                    ]
                }
            ],
        }
    )
    root = xml(render(b, tmp_path, formats=["docx"]))
    assert root.xpath("//w:p/w:r/w:ruby/w:rt//w:t/text()", namespaces=NS) == [
        "溫故知新"
    ]
    assert root.xpath("//w:ruby/w:rubyBase//w:t/text()", namespaces=NS) == [
        "學而時習之"
    ]


def test_long_annotations_are_editable_frames_and_preserve_source(tmp_path):
    b = load(ROOT / "examples/annotations.json")
    result = render(b, tmp_path, formats=["docx"])
    root = xml(result)
    texts = root.xpath("//w:txbxContent//w:t/text()", namespaces=NS)
    assert set(texts) == {n.text for n in b.annotations}
    assert not root.xpath("//w:body//wp:anchor", namespaces=NS)
    assert any("段内增删" in w for w in result.warnings)
    assert from_dict(json.loads(xml(result, "customXml/bamboo-source.xml").text)) == b


def test_horizontal_layout_reads_across_then_down():
    b = Book(
        "橫排",
        (Block((Inline("天地玄黃宇宙洪荒"),)),),
        profile=PRESETS["horizontal"].updated(rows=3, columns=3),
    )
    g = [g for page in compose(b).pages for g in page.glyphs if g.block >= 0]
    assert g[0].x < g[1].x < g[2].x and g[0].y == g[1].y
    assert g[3].y > g[0].y and g[3].x == g[0].x


def test_horizontal_double_line_notes_have_top_then_bottom_rows():
    b = Book(
        "橫排",
        (Block((Inline("天地玄黃宇宙", "note"),)),),
        profile=PRESETS["horizontal"],
    )
    g = [g for page in compose(b).pages for g in page.glyphs if g.role == "note"]
    assert g[0].y == g[2].y < g[3].y
    assert g[0].x < g[1].x < g[2].x and g[0].x == g[3].x


def test_annotations_have_non_overlapping_regions_and_every_note_character():
    b = load(ROOT / "examples/annotations.json")
    layout = compose(b)
    assert len(layout.pages[0].annotations) == 3
    actual = "".join(
        g.text for p in layout.pages for g in p.glyphs if g.role == "annotation"
    )
    expected = "".join(
        i.annotation for block in b.blocks for i in block.inlines if i.kind == "ruby"
    ) + "".join(n.text for n in b.annotations)
    assert actual == expected
    assert all(
        a.y + a.height < b.profile.margin_top
        for p in layout.pages
        for a in p.annotations
        if a.kind == "top"
    )


@pytest.mark.parametrize(
    "note",
    [
        {"text": "甲", "block": 50},
        {"text": "甲", "block": 0, "offset": 100},
        {"text": "甲" * 20, "block": 0, "columns": 1, "extent": 2},
        {"text": "甲", "block": 0, "placement": "anywhere"},
    ],
)
def test_invalid_annotation_inputs(note):
    with pytest.raises(BambooError):
        from_dict(
            {"title": "測試", "blocks": [{"text": "天地"}], "annotations": [note]}
        )


def test_top_annotation_overflow_is_not_clipped():
    b = Book(
        "測試",
        (Block((Inline("天地"),)),),
        annotations=(Annotation("甲" * 20, 0, placement="top", extent=20),),
    )
    with pytest.raises(BambooError, match="越界"):
        compose(b)


def test_annotation_anchor_cannot_be_another_note():
    with pytest.raises(BambooError, match="不能锚定"):
        Book(
            "測試",
            (Block((Inline("天地", "note"),)),),
            annotations=(Annotation("甲", 0),),
        )


def test_new_markup_keeps_footnotes_and_commentary_separate():
    b = parse("@writing-mode horizontal-tb\n## 分節\n正文((脚注))\n\n>> 段后注")
    assert b.profile.writing_mode == "horizontal-tb"
    assert b.blocks[0].level == 2
    assert b.blocks[1].inlines[1].kind == "footnote"
    assert b.blocks[2].kind == "commentary" and b.blocks[2].level == 2
