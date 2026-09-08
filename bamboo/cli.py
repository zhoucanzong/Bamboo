from __future__ import annotations

import argparse
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys

from .engine import render
from .fonts import resolve_font
from .layout import compose
from .model import BambooError, PRESETS
from .parser import load


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="bamboo", description="Bamboo 简牍古籍排版引擎"
    )
    parser.add_argument("--version", action="version", version="Bamboo 0.5.0")
    sub = parser.add_subparsers(dest="command")
    edit = sub.add_parser("edit", help="打开可直接编辑的界面")
    edit.add_argument("--port", type=int, default=8765)
    edit.add_argument("--workspace", type=Path, default=Path("output/editor"))
    edit.add_argument("--no-browser", action="store_true")
    sub.add_parser("presets", help="列出内置版式")
    for name in ("render", "check", "layout"):
        cmd = sub.add_parser(
            name,
            help={
                "render": "导出文档",
                "check": "检查源文、分页与缺字",
                "layout": "输出统一布局 JSON",
            }[name],
        )
        cmd.add_argument("source", type=Path)
        cmd.add_argument("--preset", choices=sorted(PRESETS))
        cmd.add_argument("--punctuation", choices=["judou", "keep", "hide"])
        cmd.add_argument("--writing-mode", choices=["vertical-rl", "horizontal-tb"])
        if name != "layout":
            cmd.add_argument(
                "--font", type=Path, help="TTF/OTF/TTC 字体路径，也可设置 BAMBOO_FONT"
            )
            cmd.add_argument("--font-index", type=int)
        if name == "render":
            cmd.add_argument("-o", "--output", type=Path, default=Path("output"))
            cmd.add_argument("--name", default="book")
            cmd.add_argument(
                "--formats",
                nargs="+",
                choices=["pdf", "html", "docx"],
                default=["pdf", "html", "docx"],
            )
            cmd.add_argument(
                "--docx-mode", choices=["flow", "facsimile", "editable"], default="flow"
            )
            cmd.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args(argv)
    try:
        if args.command in (None, "edit"):
            from .webapp import serve

            serve(
                port=getattr(args, "port", 8765),
                workspace=getattr(args, "workspace", "output/editor"),
                open_browser=not getattr(args, "no_browser", False),
            )
            return 0
        elif args.command == "presets":
            result = {k: asdict(v) for k, v in PRESETS.items()}
        else:
            book = load(args.source)
            profile = PRESETS[args.preset] if args.preset else book.profile
            if args.punctuation:
                profile = profile.updated(punctuation=args.punctuation)
            if args.writing_mode:
                profile = profile.updated(writing_mode=args.writing_mode)
            book = replace(book, profile=profile)
            if args.command == "render":
                result = render(
                    book,
                    args.output,
                    basename=args.name,
                    formats=args.formats,
                    font_path=args.font,
                    font_index=args.font_index,
                    docx_mode=args.docx_mode,
                    dpi=args.dpi,
                ).to_dict()
            else:
                layout = compose(book)
                if args.command == "layout":
                    result = layout.to_dict()
                else:
                    font = resolve_font(layout, args.font, args.font_index)
                    result = {
                        "valid": True,
                        "pages": len(layout.pages),
                        "font": font.family,
                        "warnings": list(layout.warnings),
                    }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (BambooError, OSError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False), file=sys.stderr)
        return 2
