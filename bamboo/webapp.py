"""Local UI adapter for EditorSession. No source-file authoring is required."""

from __future__ import annotations

import base64
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import math
from pathlib import Path
import re
import secrets
from urllib.parse import urlparse, quote
import uuid
import webbrowser

from .editor import EditorSession, RevisionConflict
from .engine import render
from .fonts import resolve_font
from .importers import import_document
from .layout import clusters
from .model import BambooError, PRESETS


class EditorApplication:
    def __init__(self, workspace):
        self.workspace = Path(workspace).resolve()
        (self.workspace / "documents").mkdir(parents=True, exist_ok=True)
        self.sessions = {}
        self.token = secrets.token_urlsafe(32)
        blank = EditorSession()
        self.font = resolve_font(blank.layout(), subset_font=False)

    def path(self, identifier):
        if not isinstance(identifier, str) or not re.fullmatch(
            r"[a-f0-9]{32}", identifier
        ):
            raise BambooError("无效文档标识")
        return self.workspace / "documents" / (identifier + ".json")

    def get(self, identifier):
        if identifier not in self.sessions:
            path = self.path(identifier)
            if not path.is_file():
                raise BambooError("文档不存在")
            self.sessions[identifier] = EditorSession.restore(
                json.loads(path.read_text())
            )
        return self.sessions[identifier]

    def persist(self, session):
        session.save(self.path(session.document_id))
        self.sessions[session.document_id] = session

    def list_documents(self):
        result = []
        for path in sorted(
            (self.workspace / "documents").glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                data = json.loads(path.read_text())
                result.append(
                    {
                        "id": path.stem,
                        "title": data["book"]["title"],
                        "revision": data["revision"],
                    }
                )
            except (ValueError, KeyError):
                continue
        return result

    def view(self, session):
        layout = session.layout()
        state = session.state()
        pages = []
        missing = set()
        for pi, page in enumerate(layout.pages):
            item = asdict(page)
            for raw, glyph in zip(item["glyphs"], page.glyphs):
                raw["baseline_x"], raw["baseline_y"] = self.font.origin(glyph)
                missing.update(
                    c for c in glyph.text if not self.font.face.has_glyph(ord(c))
                )
                if glyph.block >= 0:
                    block = session.book.blocks[glyph.block]
                    base = sum(len(i.text) for i in block.inlines[: glyph.inline])
                    raw["block_id"] = session.block_ids[glyph.block]
                    raw["start"] = base + glyph.offset
                    length = next(
                        (
                            len(c)
                            for o, c in clusters(block.inlines[glyph.inline].text)
                            if o == glyph.offset
                        ),
                        1,
                    )
                    raw["end"] = raw["start"] + length
            pages.append(item)
        issues = list(session.issues)
        if missing:
            issues.append(
                "当前字体缺少这些字，输入已保留：" + " ".join(sorted(missing)[:12])
            )
        state["view"] = {
            "pages": pages,
            "block_starts": layout.block_starts,
            "caret": session.caret(),
            "changed_pages": session.changed_pages,
            "issues": issues,
            "layout_valid": not issues,
            "font_family": self.font.family,
        }
        state["view"]["boundaries"] = {
            identifier: sorted({o for o, _ in clusters(block.text)} | {len(block.text)})
            for identifier, block in zip(session.block_ids, session.book.blocks)
        }
        state["view"]["preset"] = next(
            (name for name, p in PRESETS.items() if p == session.book.profile), "custom"
        )
        state["view"]["numbered_notes"] = [
            {
                "target": i.target,
                "text": i.text,
                "label": i.annotation,
                "boxed": i.boxed,
            }
            for b in session.book.blocks
            for i in b.inlines
            if i.kind == "numbered_note"
        ]
        return state


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(
            self,
            data,
            content_type="application/json; charset=utf-8",
            status=200,
            filename=None,
        ):
            if not isinstance(data, bytes):
                data = json.dumps(data, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Cache-Control",
                (
                    "private, max-age=3600"
                    if content_type.startswith("font/")
                    else "no-store"
                ),
            )
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; font-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'",
            )
            if filename:
                self.send_header(
                    "Content-Disposition",
                    "attachment; filename*=UTF-8''" + quote(filename),
                )
            self.end_headers()
            self.wfile.write(data)

        def _authorized(self):
            if not secrets.compare_digest(
                self.headers.get("X-Bamboo-Token", ""), app.token
            ):
                raise PermissionError("请从本地编辑界面访问")
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + self.headers.get("Host", ""):
                raise PermissionError("不接受跨站编辑请求")

        def _body(self):
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 32_000_000:
                raise BambooError("请求内容为空或超过 32MB")
            if not self.headers.get("Content-Type", "").startswith("application/json"):
                raise BambooError("需要 JSON 请求")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise BambooError("请求必须是对象")
            return data

        def do_GET(self):
            try:
                path = urlparse(self.path).path
                web = Path(__file__).parent / "web"
                if path == "/":
                    data = (
                        (web / "index.html")
                        .read_text()
                        .replace("__BAMBOO_TOKEN__", app.token)
                    )
                    self._send(data.encode(), "text/html; charset=utf-8")
                elif path in {"/assets/app.js", "/assets/style.css"}:
                    self._send(
                        (web / path.rsplit("/", 1)[1]).read_bytes(),
                        (
                            "text/javascript; charset=utf-8"
                            if path.endswith(".js")
                            else "text/css; charset=utf-8"
                        ),
                    )
                elif path == "/assets/font":
                    self._send(app.font.data, app.font.mime)
                elif path == "/api/documents":
                    self._authorized()
                    self._send({"documents": app.list_documents()})
                elif path == "/api/symbols":
                    self._authorized()
                    from .symbols import STYLES, fish_tail

                    items = []
                    for key, label in STYLES.items():
                        lines, polygons = fish_tail(key, "down", 20, 20, 28, "#31594a")
                        items.append(
                            {
                                "id": key,
                                "label": label,
                                "lines": [asdict(l) for l in lines],
                                "polygons": [asdict(p) for p in polygons],
                            }
                        )
                    self._send({"symbols": items})
                elif path.startswith("/api/document/"):
                    self._authorized()
                    self._send(app.view(app.get(path.rsplit("/", 1)[1])))
                else:
                    self._send({"error": "未找到"}, status=404)
            except PermissionError as e:
                self._send({"error": str(e)}, status=403)
            except (BambooError, ValueError, KeyError, OSError) as e:
                self._send({"error": str(e)}, status=422)

        def do_POST(self):
            try:
                self._authorized()
                data = self._body()
                path = urlparse(self.path).path
                if path == "/api/documents":
                    session = EditorSession()
                    if data.get("preset"):
                        session.dispatch(
                            {"type": "set_profile", "preset": data["preset"]}
                        )
                    app.persist(session)
                    self._send(app.view(session))
                    return
                if path == "/api/import":
                    session, warnings = import_document(
                        base64.b64decode(data["data"], validate=True),
                        data.get("filename", "文档.txt"),
                    )
                    session.document_id = uuid.uuid4().hex
                    app.persist(session)
                    state = app.view(session)
                    state["import_warnings"] = warnings
                    self._send(state)
                    return
                parts = path.strip("/").split("/")
                if len(parts) != 3 or parts[0] != "api":
                    self._send({"error": "未找到"}, status=404)
                    return
                _, action, identifier = parts
                session = app.get(identifier)
                if action == "command":
                    session.dispatch(
                        data["commands"], expected_revision=data.get("revision")
                    )
                    app.persist(session)
                    self._send(app.view(session))
                elif action == "select":
                    session.select(data["anchor"], data.get("focus"))
                    self._send(
                        {
                            "selection": asdict(session.selection),
                            "caret": session.caret(),
                        }
                    )
                elif action == "hit":
                    coords = [data.get("x"), data.get("y")]
                    if any(
                        type(v) not in (int, float) or not math.isfinite(v)
                        for v in coords
                    ):
                        raise BambooError("无效点击坐标")
                    self._send(
                        {
                            "position": asdict(
                                session.hit_test(data.get("page", 0), *coords)
                            )
                        }
                    )
                elif action == "save":
                    app.persist(session)
                    self._send(
                        {"editor_schema": 1, **session.state()},
                        filename=session.book.title + ".json",
                    )
                elif action == "export":
                    format_name = data.get("format", "docx")
                    if format_name not in {"pdf", "html", "docx"}:
                        raise BambooError("不支持的导出格式")
                    directory = app.workspace / "exports" / uuid.uuid4().hex
                    result = render(session.book, directory, formats=[format_name])
                    content_type = {
                        "pdf": "application/pdf",
                        "html": "text/html; charset=utf-8",
                        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    }[format_name]
                    self._send(
                        Path(result.files[format_name]).read_bytes(),
                        content_type,
                        filename=session.book.title + "." + format_name,
                    )
                else:
                    self._send({"error": "未找到"}, status=404)
            except RevisionConflict as e:
                self._send({"error": str(e), "conflict": True}, status=409)
            except PermissionError as e:
                self._send({"error": str(e)}, status=403)
            except (BambooError, ValueError, KeyError, TypeError, OSError) as e:
                self._send({"error": str(e)}, status=422)

    return Handler


def serve(port=8765, workspace="output/editor", open_browser=True):
    app = EditorApplication(workspace)
    server = HTTPServer(("127.0.0.1", port), make_handler(app))
    url = f"http://127.0.0.1:{server.server_port}"
    print(
        f"Bamboo 编辑器：{url}\n文档自动保存在：{app.workspace}\n按 Ctrl+C 停止服务。",
        flush=True,
    )
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
