"""Validated semantic document and immutable, backend-neutral page geometry.

Coordinates are points (1/72 inch), measured from the top-left of the page.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
import math
import re
from typing import Any, Tuple


class BambooError(ValueError):
    """An actionable input, layout or export error."""


@dataclass(frozen=True)
class Inline:
    text: str
    kind: str = "text"
    annotation: str = ""
    target: str = ""
    boxed: bool = True

    def __post_init__(self):
        if type(self.boxed) is not bool:
            raise BambooError("boxed 必须为布尔值")
        if not isinstance(self.kind, str) or self.kind not in {
            "text",
            "note",
            "footnote",
            "ruby",
            "emphasis",
            "label",
            "numbered_note",
        }:
            raise BambooError(f"未知行内类型: {self.kind}")
        if not isinstance(self.text, str) or not self.text:
            raise BambooError("行内文本必须是非空字符串")
        if any(ord(c) < 32 and c not in "\n\t\r" for c in self.text):
            raise BambooError("文本包含不允许的控制字符")
        if not isinstance(self.annotation, str) or any(
            ord(c) < 32 for c in self.annotation
        ):
            raise BambooError("旁注文本必须是不含控制字符的字符串")
        if self.kind == "ruby" and not self.annotation:
            raise BambooError("ruby 必须提供 annotation")
        if self.kind not in {"ruby", "numbered_note"} and self.annotation:
            raise BambooError("此行内类型不支持 annotation")
        if self.kind == "numbered_note":
            if not isinstance(self.target, str) or not re.fullmatch(
                r"[A-Za-z0-9_-]{1,80}", self.target
            ):
                raise BambooError("编号注文需要唯一的 target 标识")
            if len(self.annotation) > 8:
                raise BambooError("注家标签最多 8 字")
        elif self.target:
            raise BambooError("只有编号注文可以设置 target")
        if self.kind == "label" and len(self.text) > 8:
            raise BambooError("带框标签最多 8 字")
        if self.kind == "ruby" and (len(self.text) > 8 or len(self.annotation) > 16):
            raise BambooError(
                "原生短旁注最多锚定 8 字、注文 16 字；长批注应使用 annotations"
            )


@dataclass(frozen=True)
class Block:
    inlines: Tuple[Inline, ...] = ()
    kind: str = "paragraph"
    indent: int = 0
    level: int = 1

    def __post_init__(self):
        if not isinstance(self.kind, str) or self.kind not in {
            "paragraph",
            "heading",
            "commentary",
            "pagebreak",
        }:
            raise BambooError(f"未知段落类型: {self.kind}")
        if type(self.indent) is not int or self.indent < 0:
            raise BambooError("缩进必须是非负整数")
        if type(self.level) is not int or not 1 <= self.level <= 9:
            raise BambooError("层级 level 必须为 1 到 9 的整数")
        object.__setattr__(self, "inlines", tuple(self.inlines))
        if self.kind == "pagebreak" and self.inlines:
            raise BambooError("分页符不能带正文")
        if any(not isinstance(x, Inline) for x in self.inlines):
            raise BambooError("inlines 必须包含 Inline")

    @property
    def text(self):
        return "".join(i.text for i in self.inlines)


@dataclass(frozen=True)
class Profile:
    writing_mode: str = "vertical-rl"
    width: float = 842
    height: float = 595
    margin_x: float = 42
    margin_top: float = 48
    margin_bottom: float = 48
    columns: int = 10  # per panel
    rows: int = 20
    panels: int = 2
    spine: float = 0
    font_size: float = 19
    punctuation: str = "judou"
    border: str = "none"
    rules: bool = False
    fish_tail: bool = False
    fish_tail_style: str = "solid"
    fish_tail_direction: str = "auto"
    spine_rules: bool = True
    show_title: bool = True
    show_volume: bool = True
    show_page_number: bool = True
    ink: str = "#24221f"
    rule_color: str = "#4a4136"
    paper: str = "#ffffff"
    accent: str = "#9b3028"

    def __post_init__(self):
        if self.writing_mode not in ("vertical-rl", "horizontal-tb"):
            raise BambooError("writing_mode 必须为 vertical-rl 或 horizontal-tb")
        if self.fish_tail_style not in (
            "solid",
            "outline",
            "double",
            "notched",
            "split",
            "stepped",
        ):
            raise BambooError("未知鱼尾样式")
        if self.fish_tail_direction not in ("auto", "up", "down", "left", "right"):
            raise BambooError("未知鱼尾方向")
        for key in (
            "width",
            "height",
            "margin_x",
            "margin_top",
            "margin_bottom",
            "font_size",
        ):
            value = getattr(self, key)
            if (
                type(value) not in (int, float)
                or not math.isfinite(value)
                or value <= 0
            ):
                raise BambooError(f"{key} 必须是有限正数")
        if (
            type(self.spine) not in (int, float)
            or not math.isfinite(self.spine)
            or self.spine < 0
        ):
            raise BambooError("spine 必须是有限非负数")
        for key in ("columns", "rows", "panels"):
            if type(getattr(self, key)) is not int or getattr(self, key) < 1:
                raise BambooError(f"{key} 必须是正整数")
        if self.panels not in (1, 2):
            raise BambooError("panels 仅支持 1 或 2")
        for key in (
            "rules",
            "fish_tail",
            "spine_rules",
            "show_title",
            "show_volume",
            "show_page_number",
        ):
            if type(getattr(self, key)) is not bool:
                raise BambooError(f"{key} 必须为布尔值")
        if not isinstance(self.punctuation, str) or self.punctuation not in {
            "judou",
            "keep",
            "hide",
        }:
            raise BambooError("punctuation 应为 judou、keep 或 hide")
        if not isinstance(self.border, str) or self.border not in {
            "single",
            "double",
            "none",
        }:
            raise BambooError("border 应为 single、double 或 none")
        for key in ("ink", "rule_color", "paper", "accent"):
            if not isinstance(getattr(self, key), str) or not re.fullmatch(
                r"#[0-9a-fA-F]{6}", getattr(self, key)
            ):
                raise BambooError(f"{key} 必须是 #RRGGBB 颜色")
        if (
            self.width > 14400
            or self.height > 14400
            or self.columns > 200
            or self.rows > 500
        ):
            raise BambooError("页面或字格参数过大")
        if self.font_size < 4 or self.font_size > min(
            self.line_advance * 0.8, self.cell_advance * 0.9
        ):
            raise BambooError("字号无法放入字格，请调整页面、边距、行数或字号")
        if min(self.margin_x, self.margin_top, self.margin_bottom) < 8:
            raise BambooError("边距至少为 8pt，以容纳外框")

    @property
    def body_height(self):
        return self.height - self.margin_top - self.margin_bottom

    @property
    def panel_width(self):
        return (self.width - 2 * self.margin_x - self.spine) / self.panels

    @property
    def column_width(self):
        return self.panel_width / self.columns

    @property
    def row_height(self):
        return self.body_height / self.rows

    @property
    def vertical(self):
        return self.writing_mode == "vertical-rl"

    @property
    def line_advance(self):
        return (self.panel_width if self.vertical else self.body_height) / self.columns

    @property
    def cell_advance(self):
        return (self.body_height if self.vertical else self.panel_width) / self.rows

    def updated(self, **kwargs):
        try:
            return replace(self, **kwargs)
        except TypeError as e:
            raise BambooError(f"无效版式参数: {e}") from e


PRESETS = {
    "blank": Profile(
        width=460,
        height=650,
        panels=1,
        columns=10,
        rows=22,
        font_size=20,
        margin_x=32,
        punctuation="keep",
        spine_rules=False,
        show_title=False,
        show_volume=False,
        show_page_number=False,
    ),
    "woodblock": Profile(
        spine=32, border="double", rules=True, fish_tail=True, paper="#fffdf6"
    ),
    "red-ruled": Profile(
        spine=32,
        border="double",
        rules=True,
        fish_tail=True,
        rule_color="#aa4539",
        paper="#fffaf0",
        accent="#aa4539",
    ),
    "single": Profile(
        width=460,
        height=650,
        panels=1,
        columns=10,
        rows=22,
        font_size=20,
        margin_x=32,
        margin_top=48,
        margin_bottom=48,
        spine=32,
        border="double",
        rules=True,
        fish_tail=True,
        paper="#fffdf6",
    ),
    "horizontal": Profile(
        writing_mode="horizontal-tb",
        width=595,
        height=842,
        panels=1,
        columns=26,
        rows=24,
        font_size=16,
        margin_x=48,
        spine=0,
        punctuation="keep",
        rules=False,
        fish_tail=False,
    ),
}


@dataclass(frozen=True)
class Annotation:
    text: str
    block: int
    inline: int = 0
    offset: int = 0
    placement: str = "side"
    columns: int = 1
    extent: int = 12

    def __post_init__(self):
        if (
            not isinstance(self.text, str)
            or not self.text
            or any(ord(c) < 32 for c in self.text)
        ):
            raise BambooError("批注必须是非空、不含控制字符的字符串")
        for name in ("block", "inline", "offset"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 0:
                raise BambooError(f"批注 {name} 必须是非负整数")
        if self.placement not in ("side", "top"):
            raise BambooError("批注位置必须为 side 或 top")
        if type(self.columns) is not int or not 1 <= self.columns <= 4:
            raise BambooError("批注列数必须为 1 到 4")
        if type(self.extent) is not int or not 1 <= self.extent <= 100:
            raise BambooError("批注每列字数必须为 1 到 100")
        if len(self.text) > self.columns * self.extent:
            raise BambooError("批注超过指定区域容量，请增加列数或每列字数")


@dataclass(frozen=True)
class Book:
    title: str
    blocks: Tuple[Block, ...]
    volume: str = "卷一"
    author: str = ""
    profile: Profile = field(default_factory=Profile)
    annotations: Tuple[Annotation, ...] = ()

    def __post_init__(self):
        for key in ("title", "volume", "author"):
            value = getattr(self, key)
            if not isinstance(value, str) or any(ord(c) < 32 for c in value):
                raise BambooError(f"{key} 必须是不含控制字符的字符串")
        if not self.title.strip():
            raise BambooError("书名不能为空")
        object.__setattr__(self, "blocks", tuple(self.blocks))
        if any(not isinstance(b, Block) for b in self.blocks):
            raise BambooError("blocks 必须包含 Block")
        if not self.blocks or not any(b.kind != "pagebreak" for b in self.blocks):
            raise BambooError("文档必须至少包含一个正文段落")
        if not isinstance(self.profile, Profile):
            raise BambooError("profile 必须是 Profile")
        if any(b.indent >= self.profile.rows for b in self.blocks):
            raise BambooError("缩进必须小于每栏字数")
        ids = [
            i.target
            for b in self.blocks
            for i in b.inlines
            if i.kind == "numbered_note"
        ]
        if len(ids) != len(set(ids)):
            raise BambooError("编号注文标识不能重复")
        object.__setattr__(self, "annotations", tuple(self.annotations))
        for note in self.annotations:
            if not isinstance(note, Annotation) or note.block >= len(self.blocks):
                raise BambooError("批注锚定段落不存在")
            block = self.blocks[note.block]
            if note.inline >= len(block.inlines) or note.offset >= len(
                block.inlines[note.inline].text
            ):
                raise BambooError("批注锚定的行内位置不存在")
            if block.inlines[note.inline].kind not in {"text", "emphasis"}:
                raise BambooError("独立批注必须锚定正文或重点文字，不能锚定另一条注释")


@dataclass(frozen=True)
class Glyph:
    text: str
    x: float
    y: float
    width: float
    height: float
    size: float
    role: str = "body"
    block: int = -1
    inline: int = -1
    offset: int = -1
    color: str = "#24221f"
    annotation_id: str = ""
    reference_id: str = ""


@dataclass(frozen=True)
class Line:
    x1: float
    y1: float
    x2: float
    y2: float
    width: float = 0.5
    color: str = "#24221f"


@dataclass(frozen=True)
class Polygon:
    points: Tuple[Tuple[float, float], ...]
    color: str = "#24221f"


@dataclass(frozen=True)
class AnnotationBox:
    id: str
    kind: str
    block: int
    inline: int
    offset: int
    x: float
    y: float
    width: float
    height: float
    size: float
    text: str


@dataclass(frozen=True)
class Page:
    number: int
    glyphs: Tuple[Glyph, ...]
    lines: Tuple[Line, ...]
    polygons: Tuple[Polygon, ...]
    annotations: Tuple[AnnotationBox, ...] = ()


@dataclass(frozen=True)
class Layout:
    book: Book
    pages: Tuple[Page, ...]
    warnings: Tuple[str, ...] = ()
    block_starts: Tuple[dict, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, **asdict(self)}
