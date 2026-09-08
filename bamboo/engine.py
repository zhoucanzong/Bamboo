"""Public build API. All exporters finish in staging before outputs are replaced."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .fonts import resolve_font
from .layout import compose
from .model import BambooError
from .exporters.pdf import export_pdf
from .exporters.html import export_html
from .exporters.docx import export_docx


@dataclass(frozen=True)
class BuildResult:
    pages: int
    files: dict
    warnings: tuple

    def to_dict(self):
        return {
            "pages": self.pages,
            "files": self.files,
            "warnings": list(self.warnings),
        }


def render(
    book,
    output_dir,
    *,
    basename="book",
    formats=("pdf", "html", "docx"),
    font_path=None,
    font_index=None,
    docx_mode="flow",
    dpi=180,
):
    if not isinstance(basename, str) or not re.fullmatch(r"[\w-]+", basename):
        raise BambooError("输出文件名只允许字母、数字、中文、下划线和连字符")
    formats = tuple(dict.fromkeys(formats))
    if not formats or set(formats) - {"pdf", "html", "docx"}:
        raise BambooError("导出格式必须是 pdf、html、docx 中的一种或多种")
    if docx_mode not in {"flow", "facsimile", "editable"}:
        raise BambooError("DOCX 模式必须是 flow 或 facsimile")
    if docx_mode == "editable":
        docx_mode = "flow"
    if type(dpi) is not int or not 72 <= dpi <= 600:
        raise BambooError("DOCX 栅格分辨率必须在 72 到 600 DPI 之间")
    layout = compose(book)
    extra_text = ""
    if "docx" in formats and docx_mode == "flow":
        extra_text = (
            book.title
            + book.volume
            + book.author
            + " 【】0123456789一二三四五六七八九十百千"
            + "".join(b.text for b in book.blocks)
        )
    font = resolve_font(layout, font_path, font_index, extra_text=extra_text)
    warnings = list(layout.warnings)
    if "docx" in formats:
        warnings.append(
            "DOCX 图片模式以整页图片保存，正文不支持重排。"
            if docx_mode == "facsimile"
            else "DOCX 使用原生横排或竖排正文与双行夹注，支持重排；最终分页由阅读器计算，装饰采用独立页眉图层。"
        )
        if docx_mode == "flow" and any(
            i.kind == "footnote" for b in book.blocks for i in b.inlines
        ):
            warnings.append(
                "脚注在 DOCX 中是原生随页脚注；固定布局 PDF/HTML 当前以随文双行小注表达。"
            )
        if docx_mode == "flow" and book.annotations:
            warnings.append(
                "短旁注原生随字流动；长旁批与眉批使用可编辑锚定框。长旁批跟随段落，段内增删文字后需要重新导出来更新精确位置；文本框不能自动跨页续框。"
            )
    if (
        book.special is not None
        and book.special.kind == "genealogy"
        and "docx" in formats
        and docx_mode == "flow"
    ):
        warnings.append(
            "族谱使用可编辑人物框、连线和传记表格。关系以人物记录为准；Word 中直接拖动框线不会修改亲属数据，回导将按记录重建世系图。"
        )
    if (
        book.special is not None
        and book.special.kind == "gift"
        and "docx" in formats
        and docx_mode == "flow"
    ):
        warnings.append(
            "专用文档保留原生文字与表格；Word 内增删记录后，回导简牍可重新计算金额大写和合计。每页小计按导出时的记录分组，Word 改字重排后可能改变页数。"
        )
    if (
        book.special is not None
        and book.special.kind == "gongche"
        and "docx" in formats
        and docx_mode == "flow"
    ):
        warnings.append(
            "工尺谱使用原生表格和合并单元格对应唱词与谱字。应用内增删后会重新分组；Word 内大幅改动合并结构后须核对对应关系。未推断调律、速度或演奏时值。"
        )
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_json = json.dumps(
        layout.to_dict()["book"], ensure_ascii=False, sort_keys=True
    )
    with tempfile.TemporaryDirectory(prefix=".bamboo-", dir=output_dir) as staging:
        staging = Path(staging)
        names = {}
        for kind in formats:
            name = f"{basename}.{kind}"
            target = staging / name
            if kind == "pdf":
                export_pdf(layout, font, target)
            elif kind == "html":
                export_html(layout, font, target)
            else:
                # Guard accidental gigapixel allocations in configurable page sizes.
                if (
                    docx_mode == "facsimile"
                    and max(p.profile.width * p.profile.height for p in layout.pages)
                    * (dpi / 72) ** 2
                    > 50_000_000
                ):
                    raise BambooError(
                        "DOCX 单页图像超过 5000 万像素，请降低 DPI 或页面尺寸"
                    )
                export_docx(layout, font, target, mode=docx_mode, dpi=dpi)
            names[kind] = name
        layout_name = f"{basename}.layout.json"
        (staging / layout_name).write_text(
            json.dumps(layout.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        names["layout"] = layout_name
        manifest = {
            "schema_version": 1,
            "engine": "bamboo",
            "engine_version": "0.6.0",
            "title": book.title,
            "pages": len(layout.pages),
            "units": "pt",
            "page_count_scope": "fixed-layout outputs; flow DOCX repaginates in the reader",
            "writing_mode": book.profile.writing_mode,
            "source_sha256": hashlib.sha256(source_json.encode()).hexdigest(),
            "font": {
                "family": font.family,
                "source": font.source,
                "sha256": hashlib.sha256(font.data).hexdigest(),
            },
            "docx_mode": docx_mode if "docx" in formats else None,
            "warnings": warnings,
            "outputs": {
                kind: {
                    "path": name,
                    "bytes": (staging / name).stat().st_size,
                    "sha256": hashlib.sha256((staging / name).read_bytes()).hexdigest(),
                }
                for kind, name in names.items()
            },
        }
        manifest_name = f"{basename}.manifest.json"
        (staging / manifest_name).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        names["manifest"] = manifest_name
        for name in names.values():
            if (output_dir / name).is_dir():
                raise BambooError(f"输出目标是目录，无法覆盖: {name}")
        for name in names.values():
            os.replace(staging / name, output_dir / name)
    return BuildResult(
        len(layout.pages),
        {kind: str(output_dir / name) for kind, name in names.items()},
        tuple(warnings),
    )
