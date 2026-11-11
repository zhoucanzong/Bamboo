"""Local stdio MCP adapter. Only this optional entry point imports the MCP SDK."""

from contextlib import closing, contextmanager
from dataclasses import asdict
import json
from pathlib import Path
import shutil
import sqlite3
import tempfile
from typing import Any, Literal, Optional

from .editor import EditorSession, RevisionConflict
from .engine import render
from .fonts import resolve_font
from .layout import compose
from .model import BambooError, PRESETS
from .parser import from_dict
from .styles import page_style_presets


def make_server(workspace):
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise BambooError(
            "启动 MCP 需要 Python 3.10+，请安装 bamboo-typesetter[mcp]。"
        ) from exc

    root = Path(workspace).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    database = root / "bamboo.sqlite3"

    @contextmanager
    def connect():
        with closing(sqlite3.connect(database)) as db, db:
            yield db

    with connect() as db:
        db.execute(
            "CREATE TABLE IF NOT EXISTS documents "
            "(id TEXT PRIMARY KEY, title TEXT NOT NULL, revision INTEGER NOT NULL, state TEXT NOT NULL)"
        )
    server = FastMCP(
        "Bamboo",
        instructions="简牍本地排版。先创建或读取原稿，使用当前 revision 编辑，再检查和导出。",
    )

    def snapshot(session):
        return {"editor_schema": 1, **session.state()}

    def encode(session):
        return json.dumps(snapshot(session), ensure_ascii=False)

    def read(document_id):
        with connect() as db:
            row = db.execute(
                "SELECT state FROM documents WHERE id=?", (document_id,)
            ).fetchone()
        if row is None:
            raise BambooError("文档不存在")
        return EditorSession.restore(json.loads(row[0]))

    def summary(session):
        return {
            "document_id": session.document_id,
            "revision": session.revision,
            "title": session.book.title,
            "block_ids": list(session.block_ids),
        }

    @server.tool()
    def list_styles() -> dict[str, Any]:
        """列出基础 preset 和创建原稿时可选的 page_style。"""
        return {
            "presets": sorted(PRESETS),
            "page_styles": {
                key: name for key, (name, _) in page_style_presets().items()
            },
        }

    @server.tool()
    def create_document(book: dict, page_style: Optional[str] = None) -> dict[str, Any]:
        """新建并保存原稿。book 示例：{"title":"读书记","preset":"blank","blocks":[{"text":"学而时习之。"}]}。
        双行夹注用段落 inlines 中的 {"kind":"note","text":"小注"}。page_style 用 list_styles 查询。
        """
        if page_style is not None:
            styles = page_style_presets()
            if page_style not in styles:
                raise BambooError("未知页面样式，请先调用 list_styles")
            overrides = book.get("profile", {})
            if not isinstance(overrides, dict):
                raise BambooError("profile 必须是对象")
            book = {**book, "profile": {**asdict(styles[page_style][1]), **overrides}}
        session = EditorSession(from_dict(book))
        with connect() as db:
            db.execute(
                "INSERT INTO documents VALUES (?, ?, ?, ?)",
                (
                    session.document_id,
                    session.book.title,
                    session.revision,
                    encode(session),
                ),
            )
        return summary(session)

    @server.tool()
    def list_documents() -> dict[str, Any]:
        """列出当前工作目录里 MCP 已保存的原稿标识、标题和版本。"""
        with connect() as db:
            rows = db.execute(
                "SELECT id, title, revision FROM documents ORDER BY rowid DESC"
            )
            return {
                "documents": [
                    {"document_id": i, "title": t, "revision": r} for i, t, r in rows
                ]
            }

    @server.tool()
    def read_document(document_id: str) -> dict[str, Any]:
        """读取当前原稿、版本、稳定段落标识与选区。"""
        return snapshot(read(document_id))

    @server.tool()
    def edit_document(
        document_id: str, expected_revision: int, commands: list[dict]
    ) -> dict[str, Any]:
        """原子应用 1–100 条简牍编辑命令，例如 [{"type":"insert_text","text":"学而时习之"}]。
        范围用 selection.anchor / focus 的 block_id、offset 指定。版本冲突后应重新读取。
        """
        session = read(document_id)
        if any(c.get("type") in ("undo", "redo") for c in commands):
            raise BambooError("MCP 不保留交互式撤销历史，请提交明确的修改命令")
        session.dispatch(commands, expected_revision=expected_revision)
        with connect() as db:
            # Compare again at write time: two clients may share the same directory.
            changed = db.execute(
                "UPDATE documents SET title=?, revision=?, state=? WHERE id=? AND revision=?",
                (
                    session.book.title,
                    session.revision,
                    encode(session),
                    document_id,
                    expected_revision,
                ),
            )
            if changed.rowcount != 1:
                raise RevisionConflict("文档已更新，请重新读取当前版本")
        return summary(session)

    @server.tool()
    def check_document(document_id: str) -> dict[str, Any]:
        """检查原稿排版和字体覆盖，返回固定版页数、实际字体及排版提示。"""
        session = read(document_id)
        layout = compose(session.book)
        font = resolve_font(layout)
        return {
            "document_id": document_id,
            "revision": session.revision,
            "pages": len(layout.pages),
            "font": font.family,
            "warnings": list(layout.warnings),
        }

    @server.tool()
    def export_document(
        document_id: str,
        formats: Optional[list[Literal["pdf", "html", "docx"]]] = None,
        docx_mode: Literal["flow", "facsimile"] = "flow",
    ) -> dict[str, Any]:
        """导出当前版本到独立目录；返回服务所在电脑上的绝对路径，包括可在编辑器打开的原稿。默认流式 Word。"""
        session = read(document_id)
        out = root / "exports"
        out.mkdir(exist_ok=True)
        run = Path(tempfile.mkdtemp(prefix="book-", dir=out))
        try:
            result = render(
                session.book,
                run,
                formats=("pdf", "html", "docx") if formats is None else formats,
                docx_mode=docx_mode,
            ).to_dict()
            source = run / "source.json"
            source.write_text(
                json.dumps(asdict(session.book), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            result["files"]["source"] = str(source)
        except Exception:
            shutil.rmtree(run)
            raise
        return {"document_id": document_id, "revision": session.revision, **result}

    return server
