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
    return Book("礼簿", (Block(),), profile=p, special=GiftLedger(records))


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
