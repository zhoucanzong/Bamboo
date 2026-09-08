from dataclasses import replace
import hashlib
from pathlib import Path
import json
import zipfile
import uuid
from io import BytesIO
from unittest.mock import patch

import fitz
from lxml import etree
import pytest

from bamboo import BambooError, parse, render, compose, from_dict
from bamboo.fonts import resolve_font
from bamboo.cli import main
from fontTools.ttLib import TTFont

NS = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
}


@pytest.fixture(scope="module")
def exported(tmp_path_factory):
    b = parse("@title 简牍\n# 題名\n\n甲乙[[天地玄黃]]{{宇宙}}。\n\n---\n日月盈昃。")
    out = tmp_path_factory.mktemp("exports")
    return b, render(b, out, basename="sample", dpi=72, docx_mode="facsimile")


def test_pdf_has_real_text_font_and_expected_pages(exported):
    b, result = exported
    with fitz.open(result.files["pdf"]) as doc:
        assert len(doc) == result.pages == 2
        text = "".join(p.get_text() for p in doc).replace("\n", "")
        assert "天地玄黃" in text
        assert doc[0].get_fonts()
        assert doc.get_toc()[0][1] == "題名"
        assert doc[0].rect.width == b.profile.width


def test_html_is_offline_selectable_and_uses_pdf_geometry(exported):
    b, result = exported
    text = Path(result.files["html"]).read_text()
    assert "@font-face" in text and "base64," in text
    assert text.count('<section class="leaf"') == 2
    assert "data-source=" in text and "<small>〔天地玄黃〕</small>" in text
    assert "<script src=" not in text and "<link " not in text
    layout = compose(b)
    font = resolve_font(layout)
    g = next(g for g in layout.pages[0].glyphs if g.role == "body")
    x, y = font.origin(g)
    assert f'x="{x:.5f}" y="{y:.5f}"' in text


def test_docx_facsimile_has_one_page_anchor_per_leaf_and_recoverable_source(exported):
    b, result = exported
    with zipfile.ZipFile(result.files["docx"]) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        assert len(root.findall(".//wp:anchor", NS)) == result.pages
        assert (
            len([n for n in z.namelist() if n.startswith("word/media/")])
            == result.pages
        )
        source = json.loads(
            etree.fromstring(z.read("customXml/bamboo-source.xml")).text
        )
        assert from_dict(source) == b
        assert (
            len(
                root.xpath(
                    "//w:pageBreakBefore[not(@w:val) or @w:val='1' or @w:val='true']",
                    namespaces=NS,
                )
            )
            == 1
        )


def test_manifest_hashes_match_artifacts(exported):
    _, result = exported
    manifest = json.loads(Path(result.files["manifest"]).read_text())
    assert manifest["pages"] == result.pages
    for kind, info in manifest["outputs"].items():
        data = Path(result.files[kind]).read_bytes()
        assert len(data) == info["bytes"]
        assert hashlib.sha256(data).hexdigest() == info["sha256"]


def test_editable_alias_preserves_vertical_text_and_native_notes(tmp_path):
    b = parse("@title 試書\n# 題\n\n正文[[小注]]末尾")
    result = render(b, tmp_path, formats=["docx"], docx_mode="editable")
    with zipfile.ZipFile(result.files["docx"]) as z:
        root = etree.fromstring(z.read("word/document.xml"))
        assert "".join(root.xpath("//w:t/text()", namespaces=NS)) == "題正文小注末尾"
        assert root.xpath("//w:textDirection/@w:val", namespaces=NS) == ["tbRl"]
        assert root.xpath("//w:eastAsianLayout/@w:combine", namespaces=NS) == ["1"]
        assert not root.findall(".//wp:anchor", NS)
        assert not root.findall(".//w:pBdr", NS)
        font_table = etree.fromstring(z.read("word/fontTable.xml"))
        keys = font_table.xpath("//w:embedRegular/@w:fontKey", namespaces=NS)
        assert len(keys) == 1
        mask = uuid.UUID(keys[0]).bytes[::-1]
        data = bytearray(z.read("word/fonts/bamboo.odttf"))
        for i in range(32):
            data[i] ^= mask[i % 16]
        embedded = TTFont(BytesIO(data))
        assert set(map(ord, "試書卷一題正文小注末尾")) <= set(embedded.getBestCmap())


def test_font_subset_is_repeatable():
    layout = compose(parse("@title 試書\n甲乙丙"))
    assert resolve_font(layout).data == resolve_font(layout).data


def test_html_escapes_untrusted_text(tmp_path):
    b = from_dict(
        {
            "title": "<script>alert(1)</script>",
            "blocks": [{"text": "<img src=x onerror=alert(1)>"}],
        }
    )
    result = render(b, tmp_path, formats=["html"])
    value = Path(result.files["html"]).read_text()
    assert "<img src=x" not in value and "<script>alert" not in value
    assert "&lt;img" in value


def test_export_failure_does_not_replace_existing_files(tmp_path):
    previous = tmp_path / "book.pdf"
    previous.write_bytes(b"original")
    with patch(
        "bamboo.engine.export_html", side_effect=OSError("simulated disk failure")
    ):
        with pytest.raises(OSError):
            render(parse("甲"), tmp_path)
    assert previous.read_bytes() == b"original"
    assert not (tmp_path / "book.manifest.json").exists()
    assert not list(tmp_path.glob(".bamboo-*"))


def test_missing_glyph_fails_before_writing_outputs(tmp_path):
    with pytest.raises(BambooError, match="缺少字符"):
        render(parse("甲\U0010ffff"), tmp_path)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "kwargs",
    [
        {"basename": "../escape"},
        {"formats": ["png"]},
        {"formats": []},
        {"dpi": 0},
        {"docx_mode": "unknown"},
    ],
)
def test_invalid_export_arguments(tmp_path, kwargs):
    with pytest.raises(BambooError):
        render(parse("甲"), tmp_path, **kwargs)


def test_cli_error_exit_code_and_json(tmp_path, capsys):
    source = tmp_path / "invalid.json"
    source.write_text('{"title":"甲","blocks":"wrong"}')
    assert main(["check", str(source)]) == 2
    assert "error" in json.loads(capsys.readouterr().err)
