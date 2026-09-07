from dataclasses import replace
import math
import random

import pytest

from bamboo import BambooError, Block, Book, Inline, Profile, compose, parse, from_dict
from bamboo.layout import clusters, validate_layout


def book(text="天地玄黃", **config):
    return Book("測試", (Block((Inline(text),)),), profile=Profile().updated(**config))


def body(layout):
    return [g for p in layout.pages for g in p.glyphs if g.block >= 0]


def test_right_to_left_and_right_panel_first():
    layout = compose(book("甲" * 9, columns=2, rows=2, font_size=19))
    glyphs = body(layout)
    assert len(layout.pages) == 2
    assert glyphs[0].x == glyphs[1].x
    assert glyphs[0].y < glyphs[1].y
    assert glyphs[2].x < glyphs[0].x
    assert glyphs[4].x < layout.book.profile.width / 2
    assert glyphs[8].x == glyphs[0].x


@pytest.mark.parametrize("count,pages", [(1, 1), (8, 1), (9, 2), (16, 2), (17, 3)])
def test_exact_page_boundaries(count, pages):
    assert len(compose(book("字" * count, columns=2, rows=2)).pages) == pages


def test_explicit_breaks_no_empty_leading_or_trailing_pages():
    b = book()
    b = replace(
        b,
        blocks=(
            Block(kind="pagebreak"),
            b.blocks[0],
            Block(kind="pagebreak"),
            Block(kind="pagebreak"),
            b.blocks[0],
            Block(kind="pagebreak"),
        ),
    )
    assert len(compose(b).pages) == 2


def test_note_crosses_columns_and_pages_in_reading_order():
    text = "天地玄黃宇宙洪荒日月盈昃辰宿列張寒來暑往秋收冬藏" * 4
    b = book(columns=2, rows=2)
    b = replace(b, blocks=(Block((Inline("甲"), Inline(text, "note"), Inline("乙"))),))
    out = compose(b)
    notes = [g for g in body(out) if g.role == "note"]
    assert "".join(g.text for g in notes) == text
    assert len(out.pages) > 1
    assert notes[0].x > notes[2].x
    assert notes[0].y == notes[2].y
    assert notes[0].size == b.profile.font_size / 2
    assert body(out)[-1].text == "乙"


def test_judou_does_not_consume_a_cell_or_move_to_next_page():
    out = compose(book("甲乙。丙", columns=1, rows=2))
    g = body(out)
    assert g[2].role == "punctuation"
    assert g[2].x > g[1].x
    assert g[3].x < g[0].x
    assert len(out.pages) == 1


def test_hidden_punctuation_preserves_body_and_source():
    out = compose(book("甲，乙。", punctuation="hide"))
    assert "".join(g.text for g in body(out)) == "甲乙"
    assert out.book.blocks[0].text == "甲，乙。"


def test_closing_punctuation_moves_with_preceding_character():
    out = compose(book("甲乙。", punctuation="keep", rows=2))
    a, b, punct = body(out)
    assert b.x < a.x
    assert punct.x == b.x
    assert b.y < punct.y


def test_heading_kept_with_following_body_column():
    b = book("甲" * 6, columns=2, rows=2)
    b = replace(
        b, blocks=b.blocks + (Block((Inline("題"),), "heading"), Block((Inline("文"),)))
    )
    out = compose(b)
    assert len(out.pages) == 2
    assert body(out)[-2].text == "題"
    assert {g.block for g in out.pages[-1].glyphs if g.block >= 0} == {1, 2}


def test_indent_and_emphasis():
    b = replace(book(), blocks=(Block((Inline("天地", "emphasis"),), indent=2),))
    out = compose(b)
    assert body(out)[0].y == b.profile.margin_top + 2 * b.profile.row_height
    assert body(out)[0].color == b.profile.accent


def test_cjk_extension_and_variation_cluster_offsets():
    text = "甲\U00020000\U000e0100乙"
    assert clusters(text) == [(0, "甲"), (1, "\U00020000\U000e0100"), (3, "乙")]
    assert [g.offset for g in body(compose(book(text)))] == [0, 1, 3]


@pytest.mark.parametrize(
    "config",
    [
        {"rows": 0},
        {"rows": True},
        {"width": math.nan},
        {"width": math.inf},
        {"font_size": 200},
        {"margin_x": 500},
        {"ink": "red"},
        {"panels": 3},
        {"rules": "yes"},
        {"punctuation": []},
        {"border": {}},
        {"spine": -1},
    ],
)
def test_invalid_profile_is_actionable(config):
    with pytest.raises(BambooError):
        Profile().updated(**config)


def test_randomized_mixed_content_conserves_every_source_cluster():
    rng = random.Random(731)
    for _ in range(40):
        blocks = []
        for _ in range(rng.randint(1, 20)):
            spans = tuple(
                Inline(
                    "".join(rng.choices("天地玄黃宇宙洪荒，。", k=rng.randint(1, 100))),
                    rng.choice(["text", "note", "emphasis"]),
                )
                for _ in range(rng.randint(1, 4))
            )
            blocks.append(Block(spans, indent=rng.randint(0, 2)))
        b = Book(
            "隨機測試",
            tuple(blocks),
            profile=Profile().updated(
                rows=7, columns=3, punctuation=rng.choice(["hide", "judou", "keep"])
            ),
        )
        out = compose(b)
        validate_layout(out)
        assert out == compose(b)
