"""Opt-in real browser checks: BAMBOO_BROWSER_TEST=1 pytest this module."""

import json
import os
from pathlib import Path
import threading
from http.server import HTTPServer
import zipfile

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("BAMBOO_BROWSER_TEST") != "1",
    reason="Set BAMBOO_BROWSER_TEST=1 to run Chromium checks",
)


@pytest.fixture
def editor(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    from bamboo.webapp import EditorApplication, make_handler

    app = EditorApplication(tmp_path / "workspace")
    server = HTTPServer(("127.0.0.1", 0), make_handler(app))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    with playwright.sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            viewport={"width": 1480, "height": 1040}, accept_downloads=True
        )
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url)
        page.locator(".page").wait_for()
        page.evaluate("document.fonts.ready")
        yield page, app, tmp_path, playwright.expect, url
        assert not errors, errors
        browser.close()
    server.shutdown()
    thread.join()
    server.server_close()


def current(app):
    return app.get(app.list_documents()[0]["id"])


def test_direct_page_typing_split_format_undo_and_restore(editor):
    page, app, folder, expect, url = editor
    page.locator(".page svg").click(position={"x": 430, "y": 80})
    first, second = "學而時習之不亦說乎", "有朋自遠方來不亦樂乎"
    page.keyboard.insert_text(first)
    expect(page.locator("#word-count")).to_have_text(f"{len(first)} 字")
    page.keyboard.press("Enter")
    page.keyboard.insert_text(second)
    expect(page.locator("#word-count")).to_have_text(f"{len(first+second)} 字")
    assert [b.text for b in current(app).book.blocks] == [first, second]
    page.keyboard.press("Control+a")
    page.locator("#note").click()
    expect(page.locator("body")).to_have_attribute("data-revision", "4")
    assert all(i.kind == "note" for b in current(app).book.blocks for i in b.inlines)
    page.locator("#undo").click()
    expect(page.locator("body")).to_have_attribute("data-revision", "5")
    assert all(i.kind == "text" for b in current(app).book.blocks for i in b.inlines)
    page.locator("#redo").click()
    expect(page.locator("body")).to_have_attribute("data-revision", "6")
    page.reload()
    expect(page.locator("#word-count")).to_have_text(f"{len(first+second)} 字")
    assert current(app).book.blocks[1].inlines[0].kind == "note"
    page.screenshot(path=str(folder / "direct-edit.png"))


def test_rapid_typing_and_ime_commit_once(editor):
    page, app, folder, expect, url = editor
    page.locator(".page svg").click(position={"x": 430, "y": 80})
    page.keyboard.type("abcdef", delay=0)
    expect(page.locator("#word-count")).to_have_text("6 字")
    assert current(app).book.blocks[0].text == "abcdef"
    field = page.locator("#input")
    field.dispatch_event("compositionstart", {"data": ""})
    field.evaluate(
        "el => {el.value='zhongwen';el.dispatchEvent(new InputEvent('input',{data:'zhongwen',isComposing:true,bubbles:true}));}"
    )
    assert current(app).book.blocks[0].text == "abcdef"
    field.evaluate(
        "el => {el.value='中文';el.dispatchEvent(new CompositionEvent('compositionend',{data:'中文',bubbles:true}));}"
    )
    expect(page.locator("#word-count")).to_have_text("8 字")
    field.dispatch_event("input", {"data": "中文"})
    assert current(app).book.blocks[0].text == "abcdef中文"


def test_import_plain_text_direction_notes_and_three_exports(editor):
    page, app, folder, expect, url = editor
    page.locator("#file").set_input_files(
        {
            "name": "編輯稿.txt",
            "mimeType": "text/plain",
            "buffer": "山窗日暖\n竹影入簾".encode(),
        }
    )
    expect(page.locator("#title")).to_have_value("編輯稿")
    page.locator("#horizontal").click()
    expect(page.locator("#mode-label")).to_have_text("横排 · 可编辑")
    assert not current(app).book.profile.vertical
    for format_name in ("pdf", "html", "docx"):
        page.locator("#export").click()
        page.locator("select[name=format]").select_option(format_name)
        with page.expect_download() as downloaded:
            page.locator("#modal button[type=submit]").click()
        target = folder / ("export." + format_name)
        downloaded.value.save_as(target)
        assert target.stat().st_size > 100
        if format_name == "docx":
            with zipfile.ZipFile(target) as z:
                xml = z.read("word/document.xml").decode()
                assert "lrTb" in xml and "山窗日暖" in xml
        elif format_name == "pdf":
            import fitz

            with fitz.open(target) as pdf:
                assert len(pdf) == 1
        else:
            assert "山窗日暖" in target.read_text()
    with page.expect_download() as downloaded:
        page.locator("#save").click()
    target = folder / "saved.json"
    downloaded.value.save_as(target)
    saved = json.loads(target.read_text())
    assert saved["editor_schema"] == 1
    assert saved["book"]["profile"]["writing_mode"] == "horizontal-tb"


def test_page_drag_selection_and_ruby_creation(editor):
    page, app, folder, expect, url = editor
    page.locator(".page svg").click(position={"x": 430, "y": 80})
    page.keyboard.insert_text("天地玄黃")
    expect(page.locator("#word-count")).to_have_text("4 字")
    s = current(app)
    glyphs = [g for g in s.layout().pages[0].glyphs if g.block == 0]
    r = page.locator(".page svg").bounding_box()
    scale = r["width"] / s.book.profile.width
    a, b = glyphs[0], glyphs[1]
    page.mouse.move(
        r["x"] + (a.x + a.width / 2) * scale, r["y"] + (a.y + a.height * 0.2) * scale
    )
    page.mouse.down()
    page.mouse.move(
        r["x"] + (b.x + b.width / 2) * scale,
        r["y"] + (b.y + b.height * 0.8) * scale,
        steps=6,
    )
    page.mouse.up()
    expect(page.locator("#selection-info")).to_contain_text("已选择 2 字")
    page.locator("#ruby").click()
    page.locator("input[name=annotation]").fill("萬物")
    page.locator("#modal button[type=submit]").click()
    expect(page.locator("body")).to_have_attribute("data-revision", "2")
    assert s.book.blocks[0].inlines[0].kind == "ruby"
    assert s.book.blocks[0].inlines[0].annotation == "萬物"


def test_api_refuses_cross_origin_and_stale_revision(editor):
    page, app, folder, expect, url = editor
    s = current(app)
    endpoint = url + "/api/command/" + s.document_id
    assert (
        page.request.post(
            endpoint, data={"commands": [{"type": "insert_text", "text": "錯誤"}]}
        ).status
        == 403
    )
    headers = {"X-Bamboo-Token": app.token, "Origin": "https://untrusted.example"}
    assert (
        page.request.post(
            endpoint,
            headers=headers,
            data={"commands": [{"type": "insert_text", "text": "錯誤"}]},
        ).status
        == 403
    )
    headers.pop("Origin")
    assert (
        page.request.post(
            endpoint,
            headers=headers,
            data={
                "revision": 99,
                "commands": [{"type": "insert_text", "text": "錯誤"}],
            },
        ).status
        == 409
    )
    assert not s.book.blocks[0].text


def test_optional_elements_and_symbol_gallery(editor):
    page, app, folder, expect, url = editor
    expect(page.locator(".page polygon")).to_have_count(0)
    assert current(app).book.profile.spine == 0
    page.locator("#symbols").click()
    expect(page.locator(".symbol-gallery button")).to_have_count(6)
    page.screenshot(path=str(folder / "symbol-library.png"))
    page.locator("select[name=style]").select_option("outline")
    page.locator("input[name=enabled]").check()
    page.locator("#modal button[type=submit]").click()
    expect(page.locator("body")).to_have_attribute("data-revision", "1")
    assert current(app).book.profile.fish_tail
    assert not current(app).book.profile.show_title
    page.locator("#appearance").click()
    page.get_by_role("button", name="全部关闭", exact=True).click()
    page.locator("#modal button[type=submit]").click()
    expect(page.locator("body")).to_have_attribute("data-revision", "2")
    assert current(app).book.profile.spine == 0
    expect(page.locator(".page polygon")).to_have_count(0)
    page.locator("#horizontal").click()
    expect(page.locator("#mode-label")).to_have_text("横排 · 可编辑")
    assert current(app).book.profile.spine == 0 and not current(app).book.profile.rules


def test_numbered_note_dialog_and_reference_editing(editor):
    page, app, folder, expect, url = editor
    page.locator(".page svg").click(position={"x": 430, "y": 80})
    page.keyboard.insert_text("天地玄黃")
    expect(page.locator("#word-count")).to_have_text("4 字")
    page.locator("#numbered-note").click()
    page.locator("textarea[name=text]").fill("此處說明字義")
    page.locator("#modal button[type=submit]").click()
    expect(page.locator("body")).to_have_attribute("data-revision", "2")
    assert current(app).book.blocks[0].inlines[0].text == "天地玄黃"
    page.screenshot(path=str(folder / "numbered-editor.png"))
    page.locator(".reference-link").first.click()
    expect(page.locator("#modal")).to_be_visible()
    page.locator("textarea[name=text]").fill("修訂後的注文")
    page.locator("input[name=boxed]").uncheck()
    page.locator("#modal button[type=submit]").click()
    expect(page.locator("body")).to_have_attribute("data-revision", "3")
    note = next(
        i
        for b in current(app).book.blocks
        for i in b.inlines
        if i.kind == "numbered_note"
    )
    assert note.text == "修訂後的注文" and not note.boxed


def test_styles_cover_chapters_and_seals_in_ui(editor):
    page, app, folder, expect, url = editor
    page.locator(".page svg").click(position={"x": 430, "y": 80})
    page.keyboard.insert_text("讀書養心")
    expect(page.locator("#word-count")).to_have_text("4 字")
    page.locator("#text-style").select_option("poetry")
    expect(page.locator("body")).to_have_attribute("data-revision", "2")
    page.keyboard.press("Shift+Enter")
    page.keyboard.insert_text("明理致知")
    expect(page.locator("#word-count")).to_have_text("9 字")
    assert len(current(app).book.blocks) == 1
    page.locator("#styles").click()
    page.locator("#modal-font_scale").fill("0.8")
    page.locator("#modal-ink").fill("#b32624")
    page.locator("#modal-form button[type=submit]").click()
    expect(page.locator("#save-status")).to_have_text("已自动保存")
    expect(page.locator("#modal")).not_to_be_visible()
    page.locator("#chapter").click()
    page.locator("#modal-name").fill("詩文")
    page.locator("#modal-preset").select_option("poetry-page")
    page.locator("#modal-form button[type=submit]").click()
    expect(page.locator("#section-name")).to_have_text("当前篇章：詩文")
    page.locator("#seal").click()
    page.locator("#modal-seal_style").select_option("white")
    page.locator("#modal-form button[type=submit]").click()
    expect(page.locator("#word-count")).to_have_text("13 字")
    assert current(app).book.blocks[0].inlines[-1].kind == "seal"
    page.locator("#cover").click()
    page.locator("#modal-title").fill("竹簡讀書集")
    page.locator("#modal-form button[type=submit]").click()
    expect(page.locator("#page-count")).to_have_text("2 页")
    expect(page.locator("#issues")).not_to_be_visible()
    page.reload()
    expect(page.locator("#page-count")).to_have_text("2 页")
    assert current(app).book.blocks[0].section.page_type == "title-slip"
    page.screenshot(path=str(folder / "styles-editor.png"))


def test_style_sample_opens_as_editable_and_prints_mixed_sizes(editor):
    page, app, folder, expect, url = editor
    sample = Path(__file__).resolve().parents[1] / "examples/styles.json"
    page.locator("#file").set_input_files(str(sample))
    expect(page.locator("#page-count")).to_have_text("4 页")
    expect(page.locator("#issues")).not_to_be_visible()
    assert len(current(app).book.blocks) == 18
    page.locator("#zoom").select_option("0.8")
    page.screenshot(path=str(folder / "styles-sample-editor.png"))
    from bamboo import render
    import fitz

    result = render(current(app).book, folder / "export", formats=("html",))
    page.goto(Path(result.files["html"]).as_uri())
    page.evaluate("document.fonts.ready")
    pdf = folder / "printed.pdf"
    page.pdf(path=str(pdf), prefer_css_page_size=True, print_background=True)
    with fitz.open(pdf) as printed:
        assert len(printed) == 4
        assert [(round(p.rect.width), round(p.rect.height)) for p in printed] == [
            (round(p.profile.width), round(p.profile.height))
            for p in current(app).layout().pages
        ]


def test_page_style_gallery_previews_filters_and_all_new_choices(editor):
    from bamboo.styles import page_style_presets
    from tests.test_styles import NEW_PAGE_STYLES

    page, app, folder, expect, url = editor
    page.locator(".page svg").click(position={"x": 430, "y": 80})
    page.keyboard.insert_text("页面样式保留正文")
    expect(page.locator("#word-count")).to_have_text("8 字")
    page.locator("#page-templates-side").click()
    expect(page.locator(".page-style-card")).to_have_count(16)
    expect(page.locator("#page-style-apply")).to_be_disabled()
    page.set_viewport_size({"width": 1480, "height": 1400})
    page.evaluate("document.fonts.ready")
    page.screenshot(path=str(folder / "page-style-gallery.png"))
    page.locator("#page-style-category").select_option("横排阅读")
    expect(page.locator(".page-style-card")).to_have_count(3)
    page.locator("#page-style-cancel").click()
    assert current(app).revision == 1
    ids = current(app).block_ids
    for key in sorted(NEW_PAGE_STYLES):
        page.locator("#page-templates-side").click()
        page.locator(f'[data-style="{key}"]').click()
        expect(page.locator(f'[data-style="{key}"]')).to_have_attribute(
            "aria-pressed", "true"
        )
        page.locator("#page-style-apply").click()
        expect(page.locator("#section-name")).to_have_text(
            "当前篇章：" + page_style_presets()[key][0]
        )
        expect(page.locator("#issues")).not_to_be_visible()
        assert current(app).book.blocks[0].text == "页面样式保留正文"
        assert current(app).block_ids == ids
        assert (
            current(app).book.blocks[0].section.profile == page_style_presets()[key][1]
        )
    page.locator("#undo").click()
    page.reload()
    expect(page.locator("#word-count")).to_have_text("8 字")


def test_page_style_gallery_new_chapter_scope(editor):
    page, app, folder, expect, url = editor
    page.locator(".page svg").click(position={"x": 430, "y": 80})
    page.keyboard.insert_text("前篇正文")
    expect(page.locator("#word-count")).to_have_text("4 字")
    page.keyboard.press("Enter")
    page.keyboard.insert_text("后篇正文")
    expect(page.locator("#word-count")).to_have_text("8 字")
    original = current(app).book.profile
    page.locator("#page-templates-side").click()
    page.locator('[data-style="horizontal-columns"]').click()
    page.locator("#page-style-new").check()
    page.locator("#page-style-apply").click()
    expect(page.locator("#page-count")).to_have_text("2 页")
    expect(page.locator("#issues")).not_to_be_visible()
    assert current(app).book.blocks[0].section is None
    assert current(app).book.profile == original
    assert not current(app).book.blocks[1].section.profile.vertical
