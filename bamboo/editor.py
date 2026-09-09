"""In-memory editing engine: transactions, positions, anchors, history and layout.

No file syntax, browser, HTTP server or export process is required to edit a
document. Adapters dispatch commands against the same versioned session.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, replace
import hashlib
import json
from pathlib import Path
import threading
import uuid

from .layout import clusters, compose
from .model import (
    Annotation,
    BambooError,
    Block,
    Book,
    Inline,
    PRESETS,
    SectionSpec,
    TextStyle,
)
from .parser import from_dict


class RevisionConflict(BambooError):
    """The caller must refresh its view before changing the document."""


@dataclass(frozen=True)
class Position:
    block_id: str
    offset: int = 0  # Unicode code points, at a cluster boundary


@dataclass(frozen=True)
class Selection:
    anchor: Position
    focus: Position

    @property
    def collapsed(self):
        return self.anchor == self.focus


def _id():
    return uuid.uuid4().hex


def _normalize(spans):
    result = []
    for span in spans:
        if not span.text:
            continue
        if (
            result
            and span.kind in {"text", "emphasis"}
            and result[-1].kind == span.kind
        ):
            result[-1] = replace(result[-1], text=result[-1].text + span.text)
        else:
            result.append(span)
    return tuple(result)


def _slice(spans, start, end):
    result, offset = [], 0
    for span in spans:
        a, b = max(0, start - offset), min(len(span.text), end - offset)
        if a < b:
            if span.kind in {"ruby", "numbered_note"} and (a > 0 or b < len(span.text)):
                raise BambooError("此操作会拆开关联注释，请先选择整组注释")
            result.append(replace(span, text=span.text[a:b]))
        offset += len(span.text)
    return result


class EditorSession:
    """One editable document; immutable book snapshots are its export boundary."""

    def __init__(self, book=None, *, document_id=None, block_ids=None):
        self.document_id = document_id or _id()
        self.book = book or Book(
            "未命名文档", (Block(),), volume="", profile=PRESETS["blank"]
        )
        self.block_ids = tuple(block_ids or (_id() for _ in self.book.blocks))
        if len(self.block_ids) != len(self.book.blocks) or len(
            set(self.block_ids)
        ) != len(self.block_ids):
            raise BambooError("段落标识必须唯一且与文档一致")
        first = next(i for i, b in enumerate(self.book.blocks) if b.kind != "pagebreak")
        self.selection = Selection(
            Position(self.block_ids[first]), Position(self.block_ids[first])
        )
        self.revision = 0
        self._undo, self._redo = [], []
        self._layout_revision = -1
        self._layout = None
        self._previous_pages = ()
        self.changed_pages = []
        self.issues = []
        self.lock = threading.RLock()

    def _snapshot(self):
        return self.book, self.block_ids, self.selection

    def _restore(self, snapshot):
        self.book, self.block_ids, self.selection = snapshot

    def _draft(self):
        notes = []
        for n in self.book.annotations:
            offset = (
                sum(len(i.text) for i in self.book.blocks[n.block].inlines[: n.inline])
                + n.offset
            )
            notes.append(
                {"note": n, "block_id": self.block_ids[n.block], "offset": offset}
            )
        return {
            "book": self.book,
            "blocks": list(self.book.blocks),
            "ids": list(self.block_ids),
            "notes": notes,
            "selection": self.selection,
        }

    @staticmethod
    def _position(raw):
        if isinstance(raw, Position):
            return raw
        if not isinstance(raw, dict) or set(raw) - {"block_id", "offset"}:
            raise BambooError("位置必须包含 block_id 和 offset")
        return Position(raw.get("block_id"), raw.get("offset", 0))

    def _check_position(self, draft, raw):
        pos = self._position(raw)
        if pos.block_id not in draft["ids"]:
            raise BambooError("所选段落已不存在")
        index = draft["ids"].index(pos.block_id)
        block = draft["blocks"][index]
        if block.kind == "pagebreak":
            raise BambooError("分页符不能作为文字光标位置")
        boundaries = {o for o, _ in clusters(block.text)} | {len(block.text)}
        if type(pos.offset) is not int or pos.offset not in boundaries:
            raise BambooError("光标必须位于有效的文字边界")
        return index, pos

    def _range(self, draft, command):
        raw = command.get("selection")
        selection = (
            draft["selection"]
            if raw is None
            else Selection(self._position(raw["anchor"]), self._position(raw["focus"]))
        )
        ai, a = self._check_position(draft, selection.anchor)
        bi, b = self._check_position(draft, selection.focus)
        return (ai, a, bi, b) if (ai, a.offset) <= (bi, b.offset) else (bi, b, ai, a)

    @staticmethod
    def _collapse(draft, pos):
        draft["selection"] = Selection(pos, pos)

    def _replace_text(self, draft, command, text, *, soft=False):
        if not isinstance(text, str) or any(
            ord(c) < 32 and c not in "\n\r\t" for c in text
        ):
            raise BambooError("输入必须是有效文字")
        text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "　")
        ai, a, bi, b = self._range(draft, command)
        first, last = draft["blocks"][ai], draft["blocks"][bi]
        # Edits wholly within one inline preserve its identity and annotation.
        offset = 0
        if ai == bi and "\n" not in text:
            for ii, span in enumerate(first.inlines):
                limit = offset + len(span.text)
                inside = offset <= a.offset <= b.offset <= limit and (
                    a.offset < limit or ii == len(first.inlines) - 1
                )
                if inside and (
                    span.kind in {"text", "emphasis"}
                    or offset < a.offset < limit
                    or a.offset < b.offset
                ):
                    value = (
                        span.text[: a.offset - offset]
                        + text
                        + span.text[b.offset - offset :]
                    )
                    new = list(first.inlines)
                    new[ii : ii + 1] = [replace(span, text=value)] if value else []
                    draft["blocks"][ai] = replace(first, inlines=_normalize(new))
                    self._remap_notes(
                        draft, a, b, ai, bi, text, [a.block_id], soft=soft
                    )
                    self._collapse(draft, Position(a.block_id, a.offset + len(text)))
                    return
                offset = limit
        prefix = _slice(first.inlines, 0, a.offset)
        suffix = _slice(last.inlines, b.offset, len(last.text))
        pieces = [text] if soft else text.split("\n")
        ids = [a.block_id] + [_id() for _ in pieces[1:]]
        blocks = []
        for i, value in enumerate(pieces):
            spans = (
                (prefix if i == 0 else [])
                + ([Inline(value)] if value else [])
                + (suffix if i == len(pieces) - 1 else [])
            )
            block = (
                replace(first, inlines=_normalize(spans))
                if i == 0
                else Block(
                    _normalize(spans),
                    style=first.style if first.kind == "paragraph" else "",
                )
            )
            blocks.append(block)
        self._remap_notes(draft, a, b, ai, bi, text, ids, soft=soft)
        draft["blocks"][ai : bi + 1] = blocks
        draft["ids"][ai : bi + 1] = ids
        cursor = a.offset + len(text) if len(pieces) == 1 else len(pieces[-1])
        self._collapse(draft, Position(ids[-1], cursor))

    @staticmethod
    def _remap_notes(draft, a, b, ai, bi, text, new_ids, *, soft=False):
        removed_ids = set(draft["ids"][ai : bi + 1])
        pieces = [text] if soft else text.split("\n")
        result = []
        for record in draft["notes"]:
            n = dict(record)
            if n["block_id"] not in removed_ids:
                result.append(n)
                continue
            if n["block_id"] == a.block_id and n["offset"] < a.offset:
                result.append(n)
            elif n["block_id"] == b.block_id and n["offset"] >= b.offset:
                n["block_id"] = new_ids[-1]
                n["offset"] = (
                    (a.offset + len(text) if len(pieces) == 1 else len(pieces[-1]))
                    + n["offset"]
                    - b.offset
                )
                result.append(n)
            # Deleting the anchor deletes its attached note as one undoable edit.
        draft["notes"] = result

    def _format(self, draft, command):
        ai, a, bi, b = self._range(draft, command)
        if a == b:
            raise BambooError("请先选择要设置格式的文字")
        kind = command.get("kind", "text")
        if kind == "ruby" and ai != bi:
            raise BambooError("短旁注不能跨段落")
        for index in range(ai, bi + 1):
            block = draft["blocks"][index]
            if block.kind == "pagebreak":
                continue
            start, end = (a.offset if index == ai else 0), (
                b.offset if index == bi else len(block.text)
            )
            if start == end:
                continue
            # Formatting complete ruby is allowed; cutting one is not.
            prefix, suffix = _slice(block.inlines, 0, start), _slice(
                block.inlines, end, len(block.text)
            )
            formatted = Inline(
                block.text[start:end],
                kind,
                command.get("annotation", ""),
                (command.get("target") or _id()) if kind == "numbered_note" else "",
                command.get("boxed", True),
                command.get("seal_style", "red"),
            )
            draft["blocks"][index] = replace(
                block, inlines=_normalize(prefix + [formatted] + suffix)
            )

    def _command(self, draft, command):
        if not isinstance(command, dict):
            raise BambooError("编辑命令必须是对象")
        kind = command.get("type")
        if command.get("selection"):
            raw = command["selection"]
            _, a = self._check_position(draft, raw["anchor"])
            _, b = self._check_position(draft, raw["focus"])
            draft["selection"] = Selection(a, b)
        if draft["book"].special is not None and kind not in {
            "set_special",
            "set_metadata",
            "set_profile",
            "set_direction",
            "set_font",
        }:
            raise BambooError("请通过专用记录编辑器修改这类文档")
        if kind == "set_special":
            from .structured import from_dict

            value = from_dict(command.get("value"))
            if draft["book"].special is None:
                raise BambooError("请新建对应的专用文档")
            if value.kind != draft["book"].special.kind:
                raise BambooError("不能更改专用文档类型")
            draft["book"] = replace(draft["book"], special=value)
        elif kind in {"insert_text", "replace_range"}:
            self._replace_text(draft, command, command.get("text", ""))
        elif kind == "insert_linebreak":
            self._replace_text(draft, command, "\n", soft=True)
        elif kind == "split_paragraph":
            self._replace_text(draft, command, "\n")
        elif kind in {"delete_backward", "delete_forward"}:
            ai, a, bi, b = self._range(draft, command)
            if a == b:
                block = draft["blocks"][ai]
                boundaries = sorted(
                    {o for o, _ in clusters(block.text)} | {len(block.text)}
                )
                if kind == "delete_backward":
                    if a.offset:
                        a = Position(
                            a.block_id, max(o for o in boundaries if o < a.offset)
                        )
                    elif ai:
                        previous = ai - 1
                        while (
                            previous >= 0
                            and draft["blocks"][previous].kind == "pagebreak"
                        ):
                            previous -= 1
                        if previous < 0:
                            return
                        a = Position(
                            draft["ids"][previous], len(draft["blocks"][previous].text)
                        )
                    else:
                        return
                elif b.offset < len(block.text):
                    b = Position(b.block_id, min(o for o in boundaries if o > b.offset))
                elif ai + 1 < len(draft["blocks"]):
                    following = ai + 1
                    while (
                        following < len(draft["blocks"])
                        and draft["blocks"][following].kind == "pagebreak"
                    ):
                        following += 1
                    if following == len(draft["blocks"]):
                        return
                    b = Position(draft["ids"][following], 0)
                else:
                    return
            self._replace_text(
                draft, {"selection": {"anchor": asdict(a), "focus": asdict(b)}}, ""
            )
        elif kind == "format_range":
            self._format(draft, command)
        elif kind in {"insert_inline", "add_numbered_note"}:
            if kind == "add_numbered_note":
                _, _, _, end = self._range(draft, command)
                command = {
                    **command,
                    "selection": {"anchor": asdict(end), "focus": asdict(end)},
                }
            ai, a, _, _ = self._range(draft, command)
            text = command.get("text", "")
            if "\n" in text or not text:
                raise BambooError("行内注释应为一段非空文字")
            self._replace_text(draft, command, text)
            end = draft["selection"].focus
            self._format(
                draft,
                {
                    "kind": (
                        "numbered_note"
                        if kind == "add_numbered_note"
                        else command.get("kind", "note")
                    ),
                    "annotation": command.get("annotation", ""),
                    "boxed": command.get("boxed", True),
                    "seal_style": command.get("seal_style", "red"),
                    "selection": {"anchor": asdict(a), "focus": asdict(end)},
                },
            )
        elif kind in {"update_numbered_note", "remove_numbered_note"}:
            target = command.get("target")
            match = None
            for bi, block in enumerate(draft["blocks"]):
                off = 0
                for span in block.inlines:
                    if span.kind == "numbered_note" and span.target == target:
                        match = (bi, off, span)
                    off += len(span.text)
            if match is None:
                raise BambooError("编号注文不存在")
            bi, off, span = match
            a = Position(draft["ids"][bi], off)
            b = Position(a.block_id, off + len(span.text))
            selection = {"anchor": asdict(a), "focus": asdict(b)}
            value = (
                "" if kind == "remove_numbered_note" else command.get("text", span.text)
            )
            if kind == "update_numbered_note" and not value:
                raise BambooError("注文不能为空，请使用移除")
            self._replace_text(draft, {"selection": selection}, value)
            if kind == "update_numbered_note":
                self._format(
                    draft,
                    {
                        "kind": "numbered_note",
                        "target": target,
                        "annotation": command.get("annotation", span.annotation),
                        "boxed": command.get("boxed", span.boxed),
                        "selection": {
                            "anchor": asdict(a),
                            "focus": asdict(Position(a.block_id, off + len(value))),
                        },
                    },
                )
        elif kind == "set_block":
            index, _ = self._check_position(
                draft, command.get("at", draft["selection"].focus)
            )
            values = command.get("values", {})
            if (
                set(values) - {"kind", "indent", "level", "style"}
                or values.get("kind") == "pagebreak"
            ):
                raise BambooError("无效段落属性")
            draft["blocks"][index] = replace(draft["blocks"][index], **values)
        elif kind == "set_profile":
            current, section_index = self._draft_context(draft)
            if command.get("preset"):
                if command["preset"] not in PRESETS:
                    raise BambooError("未知版式")
                profile = PRESETS[command["preset"]]
            else:
                values = dict(command.get("values", {}))
                if draft["book"].special is not None and "font_size" in values:
                    values.setdefault("rows", 1)
                    values.setdefault("columns", 1)
                profile = current.profile.updated(**values)
            self._set_draft_profile(draft, profile, section_index, command.get("scope"))
        elif kind == "set_direction":
            mode = command.get("writing_mode")
            current, section_index = self._draft_context(draft)
            p = current.profile
            if mode not in {"vertical-rl", "horizontal-tb"}:
                raise BambooError("无效文字方向")
            if mode != p.writing_mode:
                # Direction changes preserve paper and optional elements. Retune
                # only logical grid counts if needed to fit the existing type.
                import math

                inline_extent = (
                    p.body_height if mode == "vertical-rl" else p.panel_width
                )
                cross_extent = p.panel_width if mode == "vertical-rl" else p.body_height
                rows = min(
                    p.rows, max(1, math.floor(inline_extent * 0.9 / p.font_size))
                )
                columns = min(
                    p.columns, max(1, math.floor(cross_extent * 0.8 / p.font_size))
                )
                self._set_draft_profile(
                    draft,
                    p.updated(writing_mode=mode, rows=rows, columns=columns),
                    section_index,
                    command.get("scope"),
                )
        elif kind == "apply_style":
            from .styles import style_registry

            key = command.get("style")
            registry = style_registry(draft["book"])
            if key not in registry:
                raise BambooError("未知文字样式")
            ai, _, bi, _ = self._range(draft, command)
            for i in range(ai, bi + 1):
                if draft["blocks"][i].kind != "pagebreak":
                    draft["blocks"][i] = replace(
                        draft["blocks"][i], style=key, kind=registry[key].role
                    )
        elif kind == "define_style":
            from .styles import style_registry

            values = command.get("values", {})
            key = values.get("key")
            current = style_registry(draft["book"]).get(key)
            try:
                style = replace(current, **values) if current else TextStyle(**values)
            except TypeError as e:
                raise BambooError(f"无效样式属性: {e}") from e
            draft["book"] = replace(
                draft["book"],
                styles=tuple(s for s in draft["book"].styles if s.key != style.key)
                + (style,),
            )
        elif kind == "set_section":
            from .styles import page_style_presets

            current, active = self._draft_context(draft)
            index = (
                draft["ids"].index(draft["selection"].focus.block_id)
                if command.get("new")
                else (active if active is not None else 0)
            )
            values = dict(command.get("values", {}))
            if command.get("preset"):
                presets = page_style_presets()
                if command["preset"] not in presets:
                    raise BambooError("未知篇章版式")
                label, profile = presets[command["preset"]]
                values["profile"] = profile
                values.setdefault("name", label)
            elif isinstance(values.get("profile"), dict):
                values["profile"] = current.profile.updated(**values["profile"])
            try:
                spec = replace(current, **values)
            except TypeError as e:
                raise BambooError(f"无效篇章属性: {e}") from e
            draft["blocks"][index] = replace(draft["blocks"][index], section=spec)
        elif kind == "clear_section":
            _, active = self._draft_context(draft)
            if active is not None:
                draft["blocks"][active] = replace(draft["blocks"][active], section=None)
        elif kind == "insert_cover":
            title = command.get("title") or draft["book"].title
            subtitle = command.get("subtitle", "")
            base = draft["book"].profile
            cover_profile = base.updated(
                writing_mode="vertical-rl",
                columns=10,
                rows=20,
                spine=0,
                rules=False,
                fish_tail=False,
                border="none",
                paper="#ffffff",
            )
            spec = SectionSpec(
                name="封面",
                profile=cover_profile,
                page_type="title-slip",
                cover_border=command.get("border", "double"),
                cover_width=command.get("width", 70),
            )
            cover = [
                Block(
                    (Inline(title),), kind="heading", style="cover-title", section=spec
                )
            ]
            if subtitle:
                cover.append(Block((Inline(subtitle),), style="cover-subtitle"))
            if draft["blocks"][0].section is None:
                draft["blocks"][0] = replace(
                    draft["blocks"][0],
                    section=SectionSpec(name="正文", profile=base, page_number_start=1),
                )
            ids = [_id() for _ in cover]
            draft["blocks"][:0] = cover
            draft["ids"][:0] = ids
            self._collapse(draft, Position(ids[0], len(title)))
        elif kind == "set_font":
            draft["book"] = replace(draft["book"], font=command.get("font", "auto"))
        elif kind == "set_metadata":
            values = command.get("values", {})
            if set(values) - {"title", "volume", "author"}:
                raise BambooError("无效文档属性")
            draft["book"] = replace(draft["book"], **values)
        elif kind == "add_annotation":
            _, pos, _, _ = self._range(draft, command)
            index = draft["ids"].index(pos.block_id)
            if pos.offset >= len(draft["blocks"][index].text):
                raise BambooError("请选择作为批注锚点的正文文字")
            n = Annotation(
                command.get("text", ""),
                0,
                placement=command.get("placement", "side"),
                columns=command.get("columns", 1),
                extent=command.get("extent", 12),
                flow=command.get("flow", False),
                font_scale=command.get("font_scale", 0.5),
                color=command.get("color", ""),
            )
            draft["notes"].append(
                {"note": n, "block_id": pos.block_id, "offset": pos.offset}
            )
        elif kind == "update_annotation":
            index = command.get("index")
            if type(index) is not int or not 0 <= index < len(draft["notes"]):
                raise BambooError("批注不存在")
            values = command.get("values", {})
            if set(values) - {
                "text",
                "placement",
                "columns",
                "extent",
                "flow",
                "font_scale",
                "color",
            }:
                raise BambooError("无效批注属性")
            draft["notes"][index]["note"] = replace(
                draft["notes"][index]["note"], **values
            )
        elif kind == "remove_annotation":
            index = command.get("index")
            if type(index) is not int or not 0 <= index < len(draft["notes"]):
                raise BambooError("批注不存在")
            draft["notes"].pop(index)
        else:
            raise BambooError(f"未知编辑命令: {kind}")

    @staticmethod
    def _draft_context(draft):
        from .styles import section_ranges

        # Geometry context needs only the blocks, not re-indexed annotations.
        book = replace(draft["book"], blocks=tuple(draft["blocks"]), annotations=())
        index = draft["ids"].index(draft["selection"].focus.block_id)
        current = next(
            spec for begin, end, spec in section_ranges(book) if begin <= index < end
        )
        active = next(
            (i for i in range(index, -1, -1) if draft["blocks"][i].section is not None),
            None,
        )
        return current, active

    @staticmethod
    def _set_draft_profile(draft, profile, index, scope=None):
        if scope == "document" or index is None:
            draft["book"] = replace(draft["book"], profile=profile)
        else:
            b = draft["blocks"][index]
            draft["blocks"][index] = replace(
                b, section=replace(b.section, profile=profile)
            )

    @staticmethod
    def _finish(draft):
        notes = []
        for record in draft["notes"]:
            bi = draft["ids"].index(record["block_id"])
            off = record["offset"]
            for ii, span in enumerate(draft["blocks"][bi].inlines):
                if off < len(span.text):
                    notes.append(
                        replace(record["note"], block=bi, inline=ii, offset=off)
                    )
                    break
                off -= len(span.text)
            else:
                raise BambooError("编辑后的批注锚点不在正文中")
        return replace(
            draft["book"], blocks=tuple(draft["blocks"]), annotations=tuple(notes)
        )

    def dispatch(self, commands, *, expected_revision=None):
        """Commit a command or atomic command group, returning the new revision."""
        with self.lock:
            if expected_revision is not None and expected_revision != self.revision:
                raise RevisionConflict(
                    f"文档已更新：当前版本 {self.revision}，请求版本 {expected_revision}"
                )
            if isinstance(commands, dict):
                commands = [commands]
            if not isinstance(commands, list) or not commands or len(commands) > 100:
                raise BambooError("一次事务需要 1 到 100 条编辑命令")
            if len(commands) == 1 and commands[0].get("type") in {"undo", "redo"}:
                source, destination = (
                    (self._undo, self._redo)
                    if commands[0]["type"] == "undo"
                    else (self._redo, self._undo)
                )
                if source:
                    destination.append(self._snapshot())
                    self._restore(source.pop())
                    self.revision += 1
                return self.revision
            draft = self._draft()
            for command in commands:
                self._command(draft, command)
            book = self._finish(draft)
            if book.special is not None:
                compose(book)  # Reject invalid specialized geometry before committing.
            snapshot = book, tuple(draft["ids"]), draft["selection"]
            if snapshot != self._snapshot():
                self._undo.append(self._snapshot())
                self._undo = self._undo[-200:]
                self._redo.clear()
                self._restore(snapshot)
                self.revision += 1
            return self.revision

    def select(self, anchor, focus=None):
        with self.lock:
            draft = self._draft()
            _, a = self._check_position(draft, anchor)
            _, b = self._check_position(draft, focus or anchor)
            self.selection = Selection(a, b)
            return self.selection

    def layout(self):
        with self.lock:
            if self._layout_revision == self.revision:
                return self._layout
            self.issues = []
            try:
                result = compose(self.book)
            except BambooError as e:
                # Retain the edit. An annotation collision is a layout diagnostic,
                # not a reason to throw away the user's newly typed text.
                self.issues.append(str(e))
                blocks = tuple(
                    replace(
                        b,
                        style="",
                        section=(
                            replace(b.section, page_type="body") if b.section else None
                        ),
                        inlines=tuple(
                            (
                                Inline(i.text)
                                if i.kind in {"ruby", "label", "seal"}
                                else (
                                    replace(i, annotation="", boxed=False)
                                    if i.kind == "numbered_note"
                                    else i
                                )
                            )
                            for i in b.inlines
                        ),
                    )
                    for b in self.book.blocks
                )
                result = compose(
                    replace(self.book, blocks=blocks, annotations=(), styles=())
                )
            fingerprints = tuple(
                hashlib.sha256(
                    json.dumps(
                        {"page": asdict(p), "font": self.book.font},
                        ensure_ascii=False,
                        sort_keys=True,
                    ).encode()
                ).hexdigest()
                for p in result.pages
            )
            self.changed_pages = [
                i
                for i in range(max(len(fingerprints), len(self._previous_pages)))
                if i >= len(fingerprints)
                or i >= len(self._previous_pages)
                or fingerprints[i] != self._previous_pages[i]
            ]
            self._previous_pages = fingerprints
            self._layout, self._layout_revision = result, self.revision
            return result

    def _glyph_positions(self):
        for pi, page in enumerate(self.layout().pages):
            for g in page.glyphs:
                if g.block >= 0:
                    block = self.book.blocks[g.block]
                    base = sum(len(i.text) for i in block.inlines[: g.inline])
                    source = block.inlines[g.inline].text
                    length = next(
                        (len(c) for o, c in clusters(source) if o == g.offset), 1
                    )
                    yield pi, g, Position(
                        self.block_ids[g.block], base + g.offset
                    ), length

    def hit_test(self, page, x, y):
        candidates = []
        for pi, g, pos, length in self._glyph_positions():
            if pi != page:
                continue
            dx = max(g.x - x, 0, x - g.x - g.width)
            dy = max(g.y - y, 0, y - g.y - g.height)
            after = (
                y > g.y + g.height / 2
                if (self.layout().pages[page].profile or self.book.profile).vertical
                else x > g.x + g.width / 2
            )
            candidates.append(
                (
                    dx * dx + dy * dy,
                    Position(pos.block_id, pos.offset + (length if after else 0)),
                )
            )
        for start in self.layout().block_starts:
            if start["page"] == page and not self.book.blocks[start["block"]].text:
                dx = x - start["x"] - start["width"] / 2
                dy = y - start["y"] - start["height"] / 2
                candidates.append(
                    (dx * dx + dy * dy, Position(self.block_ids[start["block"]], 0))
                )
        if not candidates:
            return self.selection.focus
        return min(candidates, key=lambda item: item[0])[1]

    def caret(self, raw=None):
        pos = self._position(raw) if raw is not None else self.selection.focus
        self._check_position(self._draft(), pos)
        items = [
            (pi, g, p, n)
            for pi, g, p, n in self._glyph_positions()
            if p.block_id == pos.block_id
        ]
        exact = next((item for item in items if item[2].offset == pos.offset), None)
        after = False
        if exact is None and items:
            exact = min(
                items, key=lambda item: abs(item[2].offset + item[3] - pos.offset)
            )
            after = True
        if exact:
            page, g, _, _ = exact
            x, y, width, height = g.x, g.y, g.width, g.height
            if after:
                if (self.layout().pages[page].profile or self.book.profile).vertical:
                    y += height
                else:
                    x += width
        else:
            index = self.block_ids.index(pos.block_id)
            start = next(s for s in self.layout().block_starts if s["block"] == index)
            page, x, y, width, height = (
                start[k] for k in ("page", "x", "y", "width", "height")
            )
        if (self.layout().pages[page].profile or self.book.profile).vertical:
            return {
                "page": page,
                "x1": x + width * 0.15,
                "y1": y,
                "x2": x + width * 0.85,
                "y2": y,
            }
        return {
            "page": page,
            "x1": x,
            "y1": y + height * 0.15,
            "x2": x,
            "y2": y + height * 0.85,
        }

    def state(self):
        return {
            "document_id": self.document_id,
            "revision": self.revision,
            "book": asdict(self.book),
            "block_ids": self.block_ids,
            "selection": asdict(self.selection),
            "can_undo": bool(self._undo),
            "can_redo": bool(self._redo),
        }

    def save(self, path):
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {"editor_schema": 1, **self.state()}
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(path)

    @classmethod
    def restore(cls, data):
        if not isinstance(data, dict) or data.get("editor_schema") != 1:
            raise BambooError("不是有效的编辑文档")
        session = cls(
            from_dict(data["book"]),
            document_id=data.get("document_id"),
            block_ids=data.get("block_ids"),
        )
        session.revision = data.get("revision", 0)
        if type(session.revision) is not int or session.revision < 0:
            raise BambooError("无效文档版本")
        selection = data.get("selection")
        if selection:
            session.select(selection["anchor"], selection["focus"])
        return session
