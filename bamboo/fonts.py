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
    preferred = available_fonts().get(getattr(layout.book, "font", "auto"), {})
    chosen = path or preferred.get("path") or os.environ.get("BAMBOO_FONT")
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
            options.name_IDs += [13, 14]  # Retain the font's license metadata.
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


def available_fonts():
    """User-selected families are restricted to known local font locations."""
    candidates = {
        "wenkai": (
            "霞鹜文楷",
            [
                str(Path.home() / ".cache/bamboo/fonts/LXGWWenKai-Regular.ttf"),
                str(Path.home() / "Library/Fonts/LXGWWenKai-Regular.ttf"),
                "/Library/Fonts/LXGWWenKai-Regular.ttf",
                os.path.join(
                    os.environ.get("WINDIR", "C:/Windows"),
                    "Fonts",
                    "LXGWWenKai-Regular.ttf",
                ),
            ],
        ),
        "songti": (
            "宋体",
            [
                "/System/Library/Fonts/Supplemental/Songti.ttc",
                "/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc",
                os.path.join(
                    os.environ.get("WINDIR", "C:/Windows"), "Fonts", "simsun.ttc"
                ),
            ],
        ),
        "kaiti": (
            "楷体",
            [
                "/System/Library/Fonts/Supplemental/Kaiti.ttc",
                "/usr/share/fonts/truetype/arphic/ukai.ttc",
                os.path.join(
                    os.environ.get("WINDIR", "C:/Windows"), "Fonts", "simkai.ttf"
                ),
            ],
        ),
    }
    result = {}
    for key, (name, paths) in candidates.items():
        path = next((p for p in paths if Path(p).is_file()), None)
        if path:
            result[key] = {"name": name, "path": path}
    return result


WENKAI_REVISION = "50f4b182415a8c33d9a456df220b66a284e2509b"
WENKAI_SHA256 = "39ad71264b588165b469e35e6afb162a378dacd1f95348160240ba9038ac3009"


def install_wenkai():
    """Explicit opt-in, pinned OFL font download to the user's application cache."""
    import hashlib
    import json
    import urllib.request

    folder = Path.home() / ".cache/bamboo/fonts"
    target = folder / "LXGWWenKai-Regular.ttf"
    if (
        target.is_file()
        and hashlib.sha256(target.read_bytes()).hexdigest() == WENKAI_SHA256
        and (folder / "LXGWWenKai-OFL.txt").is_file()
    ):
        return target
    root = f"https://raw.githubusercontent.com/lxgw/LxgwWenKai/{WENKAI_REVISION}/"
    try:
        request = urllib.request.Request(
            root + "fonts/TTF/LXGWWenKai-Regular.ttf",
            headers={"User-Agent": "Bamboo-font-installer"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read(32_000_001)
        if len(data) > 32_000_000 or hashlib.sha256(data).hexdigest() != WENKAI_SHA256:
            raise BambooError("字体文件校验失败，未安装")
        with urllib.request.urlopen(root + "OFL.txt", timeout=30) as response:
            license_data = response.read(100_000)
        if b"SIL OPEN FONT LICENSE" not in license_data:
            raise BambooError("字体许可文件校验失败")
        folder.mkdir(parents=True, exist_ok=True)
        temporary = folder / "LXGWWenKai-Regular.ttf.download"
        temporary.write_bytes(data)
        temporary.replace(target)
        (folder / "LXGWWenKai-OFL.txt").write_bytes(license_data)
        (folder / "source.json").write_text(
            json.dumps(
                {
                    "url": root + "fonts/TTF/LXGWWenKai-Regular.ttf",
                    "sha256": WENKAI_SHA256,
                },
                indent=2,
            )
        )
        return target
    except BambooError:
        raise
    except (OSError, ValueError) as e:
        raise BambooError(f"字体下载失败，可稍后重试：{e}") from e
