from dataclasses import asdict, replace
from decimal import Decimal
import json
from pathlib import Path
from io import BytesIO
import zipfile

import pytest
from docx import Document
from docx.oxml.ns import qn
from bamboo import Book, Block, PRESETS, compose, render, EditorSession, BambooError
from bamboo.structured import GiftLedger, GiftRecord, money_upper, summary
from bamboo.parser import from_dict
from bamboo.importers import import_docx


def gift_book(vertical=False, count=9):
    p = PRESETS["horizontal"].updated(
        width=842,
        height=595,
        columns=20,
        rows=30,
        font_size=14,
        margin_x=36,
        margin_top=36,
        margin_bottom=36,
        border="single",
        writing_mode="vertical-rl" if vertical else "horizontal-tb",
    )
    records = tuple(
        GiftRecord(str(i), "来宾" + str(i), "100.10", "鲜花", "2026-09-09", "亲友")
        for i in range(count)
    )
    return Book("册簿", (Block(),), profile=p, special=GiftLedger(records))


@pytest.mark.parametrize(
    "value,expected",
    [
        ("0", "零元整"),
        ("0.01", "零元零壹分"),
        ("0.10", "零元壹角"),
        ("10", "壹拾元整"),
        ("1010", "壹仟零壹拾元整"),
        ("10001", "壹万零壹元整"),
        ("100010001.05", "壹亿零壹万零壹元零伍分"),
        ("999999999999.99", "玖仟玖佰玖拾玖亿玖仟玖佰玖拾玖万玖仟玖佰玖拾玖元玖角玖分"),
    ],
)
def test_uppercase_money(value, expected):
    assert money_upper(value) == expected


@pytest.mark.parametrize("value", ["-1", "NaN", "1.001", "1e3", "1000000000000", ""])
def test_invalid_money_is_rejected(value):
    with pytest.raises(BambooError):
        GiftRecord("a", "名字", value)


@pytest.mark.parametrize("vertical", [True, False])
def test_gift_pages_totals_fields_and_json(vertical):
    book = gift_book(vertical)
    layout = compose(book)
    assert len(layout.pages) == 2
    assert summary(book.special)["total"] == "900.90"
    assert from_dict(json.loads(json.dumps(asdict(book)))) == book
    for p in layout.pages:
        table = next(w for w in p.widgets if w["kind"] == "table")
        ids = {c["record"] for c in table["cells"] if c.get("record")}
        total = sum(Decimal(r.amount) for r in book.special.records if r.id in ids)
        assert any(f"本页小计：{total:.2f}" in w.get("text", "") for w in p.widgets)
    assert {g.object_id for p in layout.pages for g in p.glyphs if g.object_id} == {
        r.id for r in book.special.records
    }


def test_gift_transaction_undo_and_invalid_edit():
    s = EditorSession(gift_book(count=1))
    before = s.book
    value = asdict(before.special)
    value["records"] = [{**asdict(before.special.records[0]), "amount": "250.05"}]
    s.dispatch({"type": "set_special", "value": value})
    assert summary(s.book.special)["total"] == "250.05"
    s.dispatch({"type": "undo"})
    assert s.book == before
    with pytest.raises(BambooError):
        s.dispatch({"type": "insert_text", "text": "不应插入正文"})
    assert s.book == before


@pytest.mark.parametrize("vertical", [False, True])
def test_gift_native_word_and_live_values(tmp_path, vertical):
    book = gift_book(vertical)
    result = render(book, tmp_path)
    doc = Document(result.files["docx"])
    assert len(doc.tables) == 2
    assert bool(doc._element.findall(".//" + qn("w:textDirection")))
    cell_directions = [
        c.get(qn("w:val"))
        for c in doc._element.findall(
            ".//" + qn("w:tcPr") + "/" + qn("w:textDirection")
        )
    ]
    assert bool(cell_directions) == vertical
    imported, warnings = import_docx(Path(result.files["docx"]).read_bytes())
    assert imported.book.special == book.special
    raw = BytesIO()
    with zipfile.ZipFile(result.files["docx"]) as src, zipfile.ZipFile(raw, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "word/document.xml":
                data = data.replace(b"100.10", b"200.20")
            dst.writestr(name, data)
    changed, _ = import_docx(raw.getvalue())
    assert summary(changed.book.special)["total"] == "1801.80"


def family_book(vertical=True):
    from bamboo.structured import FamilyPerson, Genealogy

    p = gift_book(vertical, 0).profile
    people = (
        FamilyPerson("a", "张守礼", spouses=("b",), biography="耕读传家。"),
        FamilyPerson("b", "李氏"),
        FamilyPerson("c", "张文清", parents=("a", "b")),
        FamilyPerson("d", "张文和", parents=("a", "b")),
        FamilyPerson("e", "张承远", parents=("c",)),
    )
    return Book(
        "张氏族谱", (Block(),), profile=p, special=Genealogy(people, per_page=3)
    )


def test_genealogy_generations_and_cross_page_references():
    from bamboo.structured import family_generations

    book = family_book()
    levels = family_generations(book.special.records)
    assert levels == {"a": 1, "b": 1, "c": 2, "d": 2, "e": 3}
    assert book.special.records[1].spouses == ("a",)
    layout = compose(book)
    assert len(layout.pages) == 7
    graphs = [w for p in layout.pages for w in p.widgets if w["kind"] == "graph"]
    assert len(graphs) == 2
    assert any("见第2页" in node["text"] for node in graphs[0]["nodes"])
    assert any("见第1页" in node["text"] for node in graphs[1]["nodes"])
    assert {n["record"] for g in graphs for n in g["nodes"]} == {
        "a",
        "b",
        "c",
        "d",
        "e",
    }


@pytest.mark.parametrize(
    "people",
    [
        [{"id": "a", "name": "甲", "parents": ["b"]}],
        [
            {"id": "a", "name": "甲", "parents": ["b"]},
            {"id": "b", "name": "乙", "parents": ["a"]},
        ],
        [
            {"id": "a", "name": "甲", "parents": ["b"], "spouses": ["b"]},
            {"id": "b", "name": "乙"},
        ],
    ],
)
def test_invalid_genealogy_relationships(people):
    from bamboo.structured import from_dict as special_from_dict

    with pytest.raises(BambooError):
        special_from_dict({"kind": "genealogy", "records": people})


@pytest.mark.parametrize("vertical", [False, True])
def test_genealogy_exports_native_nodes_relatives_and_biographies(tmp_path, vertical):
    book = family_book(vertical)
    result = render(book, tmp_path)
    doc = Document(result.files["docx"])
    assert len(doc.tables) == 5
    nodes = [
        n for n in doc._element.iter() if n.get("id", "").startswith("JianduPerson")
    ]
    assert len(nodes) == 5
    assert any(n.get("id", "").startswith("JianduLink") for n in doc._element.iter())
    imported, warnings = import_docx(Path(result.files["docx"]).read_bytes())
    assert imported.book.special == book.special
    assert from_dict(json.loads(json.dumps(asdict(book)))) == book


def test_word_diagram_name_edit_survives_import(tmp_path):
    from lxml import etree

    book = family_book()
    result = render(book, tmp_path, formats=("docx",))
    raw = BytesIO()
    with zipfile.ZipFile(result.files["docx"]) as src, zipfile.ZipFile(raw, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "word/document.xml":
                root = etree.fromstring(data)
                for sdt in root.iter(qn("w:sdt")):
                    tag = sdt.find(qn("w:sdtPr") + "/" + qn("w:tag"))
                    if (
                        tag is not None
                        and tag.get(qn("w:val")) == "bamboo:genealogy:a:diagram_name"
                    ):
                        next(sdt.iter(qn("w:t"))).text = "张守义"
                data = etree.tostring(root)
            dst.writestr(name, data)
    imported, warnings = import_docx(raw.getvalue())
    assert imported.book.special.records[0].name == "张守义"


def score_book(vertical=True):
    from bamboo.structured import GongcheNote, GongcheScore

    notes = []
    for phrase in range(1, 6):
        for i, symbol in enumerate("上尺工凡六五乙上"):
            notes.append(
                GongcheNote(
                    f"{phrase}_{i}",
                    symbol,
                    lyric="春" if i == 0 else "风" if i == 3 else "",
                    beat="板" if i == 0 else "眼",
                    phrase=f"第{phrase}句",
                    lyric_span=3 if i == 0 else 1,
                )
            )
    return Book(
        "工尺谱",
        (Block(),),
        profile=gift_book(vertical, 0).profile,
        special=GongcheScore(tuple(notes)),
    )


@pytest.mark.parametrize("vertical", [False, True])
def test_gongche_grouping_merges_conservation_and_roundtrip(tmp_path, vertical):
    book = score_book(vertical)
    layout = compose(book)
    assert len(layout.pages) == 2
    symbols = [g for p in layout.pages for g in p.glyphs if g.field == "symbol"]
    assert len(symbols) == 40 and len({g.object_id for g in symbols}) == 40
    tables = [
        t
        for p in layout.pages
        for w in p.widgets
        if w["kind"] == "score"
        for t in w["tables"]
    ]
    assert len(tables) == 5
    assert all(
        any(
            c.get("rowspan" if vertical else "colspan") == 3 and c["field"] == "lyric"
            for c in t["cells"]
        )
        for t in tables
    )
    result = render(book, tmp_path)
    restored, warnings = import_docx(Path(result.files["docx"]).read_bytes())
    assert restored.book.special == book.special
    assert from_dict(json.loads(json.dumps(asdict(book)))) == book
    # A changed lyric must be read from the real table, not its saved source.
    raw = BytesIO()
    with zipfile.ZipFile(result.files["docx"]) as src, zipfile.ZipFile(raw, "w") as dst:
        for name in src.namelist():
            data = src.read(name)
            if name == "word/document.xml":
                data = data.replace("春".encode(), "秋".encode())
            dst.writestr(name, data)
    changed, _ = import_docx(raw.getvalue())
    assert changed.book.special.records[0].lyric == "秋"
    assert changed.book.special.records[0].lyric_span == 3


@pytest.mark.parametrize(
    "records,capacity",
    [
        ([{"id": "a", "symbol": "上", "lyric": "春", "lyric_span": 2}], 8),
        (
            [
                {"id": "a", "symbol": "上", "lyric": "春", "lyric_span": 2},
                {"id": "b", "symbol": "尺", "lyric": "风"},
            ],
            8,
        ),
        (
            [
                {"id": "a", "symbol": "上", "lyric": "春", "lyric_span": 2},
                {"id": "b", "symbol": "尺", "phrase": "第二句"},
            ],
            8,
        ),
        (
            [
                {"id": "a", "symbol": "上", "lyric": "春", "lyric_span": 2},
                {"id": "b", "symbol": "尺"},
            ],
            1,
        ),
    ],
)
def test_invalid_lyric_mapping_is_rejected(records, capacity):
    from bamboo.structured import from_dict as special_from_dict

    with pytest.raises(BambooError):
        special_from_dict({"kind": "gongche", "records": records, "per_page": capacity})


def test_old_commentary_document_keeps_content_and_uses_new_ui_name():
    from bamboo.styles import style_registry

    book = from_dict(
        {"title": "旧稿", "blocks": [{"kind": "commentary", "text": "旧稿课注内容"}]}
    )
    assert book.blocks[0].text == "旧稿课注内容"
    assert book.blocks[0].kind == "commentary"
    assert style_registry(book)["commentary"].name == "段后注"
    assert book.special is None
