"""One embedded, subset font shared by the PDF and HTML exporters."""

from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path

import fitz
from fontTools import subset
from fontTools.ttLib import TTFont, TTCollection

from .model import BambooError


class Font:
    def __init__(self, data, family, source, rights=0):
        self.data, self.family, self.source, self.rights = data, family, source, rights
        try:
            self.face = fitz.Font(fontbuffer=data)
        except Exception as e:
            raise BambooError(f"字体无法加载: {e}") from e

    def origin(self, glyph):
        width = self.face.text_length(glyph.text, fontsize=glyph.size)
        ascent, descent = self.face.ascender, self.face.descender
        return (
            glyph.x + (glyph.width - width) / 2,
            glyph.y
            + (glyph.height - (ascent - descent) * glyph.size) / 2
            + ascent * glyph.size,
        )

    @property
    def mime(self):
        return "font/otf" if self.data[:4] == b"OTTO" else "font/ttf"


def resolve_font(layout, path=None, index=None, extra_text="", subset_font=True):
    chosen = path or os.environ.get("BAMBOO_FONT")
    if not chosen:
        candidates = [
            "/System/Library/Fonts/Supplemental/Songti.ttc",
            "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
            "/usr/share/fonts/truetype/arphic/uming.ttc",
        ]
        chosen = next((f for f in candidates if Path(f).is_file()), None)
    try:
        if chosen:
            path = Path(chosen).expanduser()
            data = path.read_bytes()
            if data[:4] == b"ttcf":
                collection = TTCollection(BytesIO(data), lazy=True)
                if index is None:
                    index = next(
                        (
                            i
                            for i, f in enumerate(collection.fonts)
                            if f["name"].getDebugName(2) == "Regular"
                            and "SC" in (f["name"].getDebugName(1) or "")
                        ),
                        0,
                    )
                if type(index) is not int or not 0 <= index < len(collection.fonts):
                    raise BambooError("字体集合索引超出范围")
                font = collection.fonts[index]
            else:
                if index not in (None, 0):
                    raise BambooError("单字体文件不支持非零索引")
                font = TTFont(BytesIO(data))
            source = path.name
        else:
            if index not in (None, 0):
                raise BambooError("内置字体不支持非零索引")
            font = TTFont(BytesIO(fitz.Font("cjk").buffer))
            source = "PyMuPDF built-in CJK fallback"
        family = font["name"].getDebugName(1) or "Bamboo CJK"
        rights = font["OS/2"].fsType if "OS/2" in font else 0
        if rights & (0x2 | 0x200):
            raise BambooError("字体不允许轮廓嵌入，请通过 --font 指定可嵌入字体")
        chars = {ord(c) for page in layout.pages for g in page.glyphs for c in g.text}
        chars.update(ord(c) for c in extra_text if c not in "\r\n\t")
        missing = chars - set(font.getBestCmap())
        if missing:
            listing = " ".join(f"{chr(c)}(U+{c:04X})" for c in sorted(missing)[:20])
            raise BambooError(
                f"字体 {family} 缺少字符: {listing}；请使用覆盖这些字符的 --font"
            )
        if subset_font and not rights & 0x100:
            options = subset.Options()
            options.recalc_timestamp = False
            # AAT tables are not used by the explicit CJK glyph placement pipeline.
            options.drop_tables += ["FFTM", "feat", "meta", "morx"]
            sub = subset.Subsetter(options=options)
            sub.populate(unicodes=chars)
            sub.subset(font)
        buffer = BytesIO()
        font.recalcTimestamp = False
        font.save(buffer)
        return Font(buffer.getvalue(), family, source, rights)
    except BambooError:
        raise
    except Exception as e:
        raise BambooError(f"无法读取字体: {e}") from e
