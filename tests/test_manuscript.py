from collections import Counter
from dataclasses import asdict, replace
from pathlib import Path
from io import BytesIO
import json
import zipfile

import fitz
import pytest
from lxml import etree
from bamboo import (
    Annotation,
    Block,
    Book,
    Inline,
    PRESETS,
    compose,
    render,
    EditorSession,
    BambooError,
    load,
)
from bamboo.annotations import overlaps, ink, rect
from bamboo.fonts import available_fonts, resolve_font


def assert_complete_and_clear(book, layout):
    for i, note in enumerate(book.annotations):
        expected = Counter(note.text)
        actual = Counter(
            g.text
            for p in layout.pages
            for g in p.glyphs
            if g.annotation_id == f"annotation-{i}"
        )
        assert actual == expected
    for page in layout.pages:
        for i, box in enumerate(page.annotations):
            assert not any(
                overlaps(rect(box), rect(other)) for other in page.annotations[i + 1 :]
            )
            assert not any(
                overlaps(rect(box), ink(g)) for g in page.glyphs if g.block >= 0
            )


def test_dense_manuscript_matches_the_requested_elements():
    book = load("examples/manuscript-notes.json")
    layout = compose(book)
    assert len(layout.pages) == 2
    assert len(book.annotations) >= 16
    assert_complete_and_clear(book, layout)
    assert any(
        b.kind == "top" and b.width > b.size for b in layout.pages[0].annotations
    )
    assert {g.color for g in layout.pages[1].glyphs if g.role == "punctuation"} == {
        book.profile.punctuation_color
    }
    assert {g.color for g in layout.pages[1].glyphs if g.role == "body"} == {
        book.profile.ink
    }


@pytest.mark.parametrize("vertical", [True, False])
def test_long_annotation_continues_without_losing_text(tmp_path, vertical):
    p = PRESETS["blank"].updated(
        columns=4,
        rows=18,
        font_size=18,
        margin_top=120,
        writing_mode="vertical-rl" if vertical else "horizontal-tb",
    )
    text = "天地玄黃宇宙洪荒" * 40
    book = Book(
        "续批测试",
        (Block((Inline("甲乙丙丁戊己庚辛壬癸" * 5),)),),
        profile=p,
        annotations=(Annotation(text, 0, offset=45, flow=True, extent=100),),
    )
    layout = compose(book)
    assert len(layout.pages) > 1
    assert_complete_and_clear(book, layout)
    assert any(b.block < 0 for page in layout.pages[1:] for b in page.annotations)
    result = render(book, tmp_path, formats=("docx", "pdf"))
    with zipfile.ZipFile(result.files["docx"]) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        values = [
            "".join(box.itertext())
            for box in root.xpath("//w:txbxContent", namespaces=ns)
        ]
        assert Counter("".join(values)) == Counter(text)
        assert (
            len(
                root.xpath(
                    '//w:pageBreakBefore[not(@w:val) or @w:val="1" or @w:val="true"]',
                    namespaces=ns,
                )
            )
            >= len(layout.pages) - 1
        )


@pytest.mark.parametrize("mode", ["keep", "judou"])
def test_word_keeps_punctuation_color_separate(tmp_path, mode):
    book = Book(
        "朱色句读",
        (Block((Inline("甲，乙。"),)),),
        profile=PRESETS["blank"].updated(
            punctuation=mode, ink="#000000", punctuation_color="#ff0000"
        ),
    )
    result = render(book, tmp_path, formats=("docx",))
    with zipfile.ZipFile(result.files["docx"]) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
        red = root.xpath(
            '//w:r[w:rPr/w:color[@w:val="FF0000"]]/w:t/text()', namespaces=ns
        )
        black = root.xpath(
            '//w:r[w:rPr/w:color[@w:val="000000"]]/w:t/text()', namespaces=ns
        )
        assert "".join(red) == ("，。" if mode == "keep" else "、。")
        assert "".join(black) == "甲乙"


def test_edit_annotation_and_font_undo():
    session = EditorSession(load("examples/manuscript-notes.json"))
    before = session.book
    session.dispatch(
        {
            "type": "update_annotation",
            "index": 0,
            "values": {"text": "新的朱批", "color": "#ff0000", "font_scale": 0.4},
        }
    )
    assert session.book.annotations[0].text == "新的朱批"
    assert_complete_and_clear(session.book, session.layout())
    session.dispatch({"type": "undo"})
    assert session.book == before
    session.dispatch({"type": "set_font", "font": "songti"})
    assert session.book.font == "songti"
    session.dispatch({"type": "undo"})
    assert session.book.font == before.font


@pytest.mark.parametrize(
    "values",
    [
        {"font_scale": 0},
        {"font_scale": float("nan")},
        {"flow": "yes"},
        {"color": "red"},
    ],
)
def test_invalid_annotation_style_is_rejected(values):
    with pytest.raises(BambooError):
        Annotation("批注", 0, **values)
