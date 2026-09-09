"""Small, explicit source language plus strict JSON import; never evaluates input."""

from __future__ import annotations

import json
import re
from dataclasses import fields
from pathlib import Path

from .model import (
    Annotation,
    BambooError,
    Block,
    Book,
    Inline,
    PRESETS,
    Profile,
    TextStyle,
    SectionSpec,
)


def _keys(obj, allowed, context):
    if not isinstance(obj, dict):
        raise BambooError(f"{context} 必须是对象")
    unknown = set(obj) - set(allowed)
    if unknown:
        raise BambooError(f"{context} 含未知字段: {', '.join(sorted(unknown))}")


from .structured import from_dict as special_from_dict


def from_dict(data):
    _keys(
        data,
        {
            "schema_version",
            "title",
            "volume",
            "author",
            "preset",
            "profile",
            "blocks",
            "annotations",
            "styles",
            "special",
            "font",
        },
        "文档",
    )
    if (
        type(data.get("schema_version", 1)) is not int
        or data.get("schema_version", 1) != 1
    ):
        raise BambooError("仅支持 schema_version=1")
    preset = data.get("preset", "woodblock")
    if not isinstance(preset, str) or preset not in PRESETS:
        raise BambooError(f"未知模板: {preset}")
    config = data.get("profile", {})
    _keys(config, {f.name for f in fields(Profile)}, "版式")
    profile = PRESETS[preset].updated(**config)
    blocks = data.get("blocks")
    if not isinstance(blocks, list):
        raise BambooError("blocks 必须是数组")
    parsed = []
    for b in blocks:
        _keys(
            b,
            {"kind", "text", "inlines", "indent", "level", "style", "section"},
            "段落",
        )
        if "text" in b and "inlines" in b:
            raise BambooError("段落 text 与 inlines 不可同时使用")
        raw = b.get("inlines", [{"text": b["text"]}] if "text" in b else [])
        if not isinstance(raw, list):
            raise BambooError("inlines 必须是数组")
        spans = []
        for item in raw:
            _keys(
                item,
                {"kind", "text", "annotation", "target", "boxed", "seal_style"},
                "行内内容",
            )
            spans.append(
                Inline(
                    item.get("text"),
                    item.get("kind", "text"),
                    item.get("annotation", ""),
                    item.get("target", ""),
                    item.get("boxed", True),
                    item.get("seal_style", "red"),
                )
            )
        parsed.append(
            Block(
                tuple(spans),
                b.get("kind", "paragraph"),
                b.get("indent", 0),
                b.get("level", 1),
                b.get("style", ""),
                (
                    section_from_dict(b["section"])
                    if b.get("section") is not None
                    else None
                ),
            )
        )
    raw_notes = data.get("annotations", [])
    if not isinstance(raw_notes, list):
        raise BambooError("annotations 必须是数组")
    notes = []
    for note in raw_notes:
        _keys(note, {f.name for f in fields(Annotation)}, "批注")
        try:
            notes.append(Annotation(**note))
        except TypeError as e:
            raise BambooError(f"批注字段不完整: {e}") from e
    raw_styles = data.get("styles", [])
    if not isinstance(raw_styles, list):
        raise BambooError("styles 必须是数组")
    styles = []
    for style in raw_styles:
        _keys(style, {f.name for f in fields(TextStyle)}, "样式")
        try:
            styles.append(TextStyle(**style))
        except TypeError as e:
            raise BambooError(f"样式字段不完整: {e}") from e
    return Book(
        data.get("title", ""),
        tuple(parsed),
        data.get("volume", "卷一"),
        data.get("author", ""),
        profile,
        tuple(notes),
        tuple(styles),
        special_from_dict(data["special"]) if data.get("special") is not None else None,
        data.get("font", "auto"),
    )


def section_from_dict(data):
    _keys(data, {f.name for f in fields(SectionSpec)}, "篇章")
    values = dict(data)
    if values.get("profile") is not None:
        _keys(values["profile"], {f.name for f in fields(Profile)}, "篇章版式")
        values["profile"] = Profile(**values["profile"])
    return SectionSpec(**values)


def parse_inlines(text):
    """[[double-line note]], {{emphasis}}, ((footnote)); backslash escapes."""
    spans, buf, i = [], [], 0

    def flush():
        if buf:
            spans.append(Inline("".join(buf)))
            buf.clear()

    while i < len(text):
        if text[i] == "\\":
            if i + 1 >= len(text):
                raise BambooError("末尾转义符不完整")
            buf.append(text[i + 1])
            i += 2
        elif text[i : i + 2] in ("[[", "{{", "(("):
            flush()
            opening = text[i : i + 2]
            closing = {"[[": "]]", "{{": "}}", "((": "))"}[opening]
            j, content = i + 2, []
            while j < len(text) and text[j : j + 2] != closing:
                if text[j] == "\\" and j + 1 < len(text):
                    content.append(text[j + 1])
                    j += 2
                elif text[j : j + 2] in ("[[", "{{", "(("):
                    raise BambooError("行内标记不支持嵌套")
                else:
                    content.append(text[j])
                    j += 1
            if j == len(text):
                raise BambooError(f"缺少闭合标记 {closing}")
            spans.append(
                Inline(
                    "".join(content),
                    {"[[": "note", "{{": "emphasis", "((": "footnote"}[opening],
                )
            )
            i = j + 2
        elif text[i : i + 2] in ("]]", "}}", "))"):
            raise BambooError("发现未配对的闭合标记")
        else:
            buf.append(text[i])
            i += 1
    flush()
    return tuple(spans)


def parse(text: str) -> Book:
    """Parse .bamboo. Metadata precedes content. Blank lines start new columns."""
    meta, blocks, pending = {}, [], []

    def flush():
        if pending:
            value = "".join(pending)
            indent = len(value) - len(value.lstrip("　"))
            blocks.append(Block(parse_inlines(value[indent:]), indent=indent))
            pending.clear()

    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip(" \t\r")
        try:
            if line.startswith("@"):
                if blocks or pending:
                    raise BambooError("元数据必须位于正文之前")
                match = re.fullmatch(
                    r"@(title|volume|author|preset|writing-mode)\s+(.+)", line
                )
                if not match:
                    raise BambooError("未知或不完整的元数据指令")
                key, value = match.groups()
                if key in meta:
                    raise BambooError(f"重复的元数据: {key}")
                meta[key] = value
            elif not line:
                flush()
            elif line == "---":
                flush()
                blocks.append(Block(kind="pagebreak"))
            elif re.match(r"#{1,9} ", line):
                flush()
                marker, value = line.split(" ", 1)
                blocks.append(Block(parse_inlines(value), "heading", 1, len(marker)))
            elif re.match(r">{1,9} ", line):
                flush()
                marker, value = line.split(" ", 1)
                blocks.append(Block(parse_inlines(value), "commentary", 0, len(marker)))
            else:
                pending.append(line)
        except BambooError as e:
            raise BambooError(f"第 {number} 行: {e}") from e
    flush()
    preset = meta.pop(
        "preset",
        "horizontal" if meta.get("writing-mode") == "horizontal-tb" else "woodblock",
    )
    if preset not in PRESETS:
        raise BambooError(f"未知模板: {preset}")
    profile = PRESETS[preset]
    if "writing-mode" in meta:
        profile = profile.updated(writing_mode=meta.pop("writing-mode"))
    return Book(
        blocks=tuple(blocks), profile=profile, title=meta.pop("title", "未題名"), **meta
    )


def load(path) -> Book:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8-sig")
        return (
            from_dict(json.loads(text))
            if path.suffix.lower() == ".json"
            else parse(text)
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as e:
        raise BambooError(f"无法读取 {path.name}: {e}") from e
