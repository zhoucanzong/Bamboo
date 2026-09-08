"""Reusable paragraph styles and independent chapter/page style contexts."""

from dataclasses import replace
from .model import TextStyle, SectionSpec, PRESETS

DEFAULT_STYLES = {
    s.key: s
    for s in (
        TextStyle("body", "正文"),
        TextStyle("heading", "题名", role="heading"),
        TextStyle("chapter-title", "篇章标题", bold=True, after=1, role="heading"),
        TextStyle("preface", "序言"),
        TextStyle("poetry", "诗文分行"),
        TextStyle("commentary", "课注", font_scale=0.75, role="commentary"),
        TextStyle("author", "作者署名", font_scale=0.75, align="end"),
        TextStyle("colophon", "题跋落款", font_scale=0.75, align="end", before=1),
        TextStyle("citation", "引文", font_scale=0.85, ink="#5b554a"),
        TextStyle(
            "cover-title",
            "题签书名",
            font_scale=1.8,
            ink="#b32624",
            align="center",
            role="heading",
        ),
        TextStyle(
            "cover-subtitle", "题签卷次", font_scale=0.8, ink="#b32624", align="center"
        ),
    )
}


def style_registry(book):
    return {**DEFAULT_STYLES, **{s.key: s for s in book.styles}}


def resolve_style(book, block):
    key = block.style or (
        "heading"
        if block.kind == "heading"
        else "commentary" if block.kind == "commentary" else "body"
    )
    return style_registry(book)[key]


def section_ranges(book):
    current = SectionSpec(
        profile=book.profile, title=book.title, volume=book.volume, author=book.author
    )
    start = 0
    result = []
    for i, block in enumerate(book.blocks):
        if block.section is not None:
            if i > start:
                result.append((start, i, current))
            spec = block.section
            current = replace(
                spec,
                profile=spec.profile or current.profile,
                title=current.title if spec.title is None else spec.title,
                volume=current.volume if spec.volume is None else spec.volume,
                author=current.author if spec.author is None else spec.author,
            )
            start = i
    result.append((start, len(book.blocks), current))
    return result


def context_at(book, index):
    return next(
        spec for start, end, spec in section_ranges(book) if start <= index < end
    )


def page_style_presets():
    red = PRESETS["woodblock"].updated(
        border_color="#c52c27",
        line_color="#e1b3ad",
        fish_tail_color="#c52c27",
        paper="#ffffff",
        rows=22,
        font_size=17,
        spine_rules=False,
    )
    return {
        "red-preface": ("朱栏序言", red),
        "poetry-page": ("诗文疏排", red.updated(rows=18, font_size=18)),
        "dense-classic": ("典籍密排", red.updated(rows=26, columns=12, font_size=14)),
        "ink-book": (
            "素墨古籍",
            PRESETS["woodblock"].updated(paper="#ffffff", fish_tail_style="outline"),
        ),
        "plain-page": ("无装饰书页", PRESETS["blank"]),
        "horizontal-page": ("横排书页", PRESETS["horizontal"]),
        "single-ink": (
            "单页墨栏",
            PRESETS["single"].updated(
                spine=0,
                border="single",
                fish_tail=False,
                columns=9,
                rows=20,
                paper="#ffffff",
            ),
        ),
        "blue-manuscript": (
            "蓝栏抄本",
            PRESETS["single"].updated(
                spine=0,
                border="single",
                fish_tail=False,
                font_size=18,
                rows=21,
                rule_color="#6986a0",
                line_color="#c0d2df",
                paper="#fafcfd",
            ),
        ),
        "warm-edition": (
            "米纸刻本",
            PRESETS["woodblock"].updated(
                columns=9,
                rows=21,
                font_size=18,
                paper="#f5ecd8",
                rule_color="#806748",
                line_color="#c6b795",
                fish_tail_style="double",
            ),
        ),
        "large-print": (
            "大字疏排",
            PRESETS["blank"].updated(
                width=595,
                height=842,
                columns=8,
                rows=18,
                font_size=30,
                margin_x=48,
                border="single",
            ),
        ),
        "pocket-book": (
            "袖珍小本",
            PRESETS["blank"].updated(
                width=320,
                height=460,
                margin_x=24,
                margin_top=32,
                margin_bottom=32,
                columns=8,
                rows=20,
                font_size=12,
                border="single",
                rules=True,
                line_color="#ccc4b5",
                paper="#fffdf7",
            ),
        ),
        "annotation-page": (
            "宽栏批校",
            PRESETS["blank"].updated(
                width=595,
                height=842,
                margin_x=56,
                margin_top=100,
                margin_bottom=56,
                columns=7,
                rows=24,
                font_size=18,
                border="single",
                rules=True,
                line_color="#dfd9cf",
            ),
        ),
        "colophon-page": (
            "序跋留白",
            PRESETS["blank"].updated(
                width=595,
                height=842,
                margin_x=72,
                margin_top=144,
                margin_bottom=80,
                columns=8,
                rows=18,
                font_size=22,
                paper="#fffdf8",
            ),
        ),
        "sutra-page": (
            "经文长行",
            PRESETS["blank"].updated(
                width=842,
                height=595,
                margin_x=40,
                margin_top=36,
                margin_bottom=36,
                columns=24,
                rows=30,
                font_size=11.5,
                border="double",
                rules=True,
                line_color="#d9d3c8",
            ),
        ),
        "horizontal-study": (
            "横排研读",
            PRESETS["horizontal"].updated(
                columns=22,
                rows=26,
                border="single",
                rules=True,
                line_color="#dce3de",
                margin_top=64,
                margin_bottom=64,
            ),
        ),
        "horizontal-columns": (
            "横排双栏",
            PRESETS["horizontal"].updated(
                width=842,
                height=595,
                panels=2,
                spine=30,
                columns=20,
                rows=22,
                font_size=12,
                margin_x=42,
                border="single",
                rules=False,
                spine_rules=True,
                show_title=False,
                show_volume=False,
                show_page_number=False,
            ),
        ),
    }


PAGE_STYLE_DESCRIPTIONS = {
    "red-preface": ("古籍双面", "朱色外框与浅红界栏，适合序言及书前说明。"),
    "poetry-page": ("古籍双面", "减少每栏字数，保留诗句分行与疏朗留白。"),
    "dense-classic": ("古籍双面", "小字密栏，适合篇幅较长的典籍正文。"),
    "ink-book": ("古籍双面", "白纸墨栏与空心鱼尾，适合素墨古籍。"),
    "plain-page": ("单页竖排", "无边框与版心，便于自由编辑和自定义。"),
    "horizontal-page": ("横排阅读", "标准横排页面，适合现代阅读及整理稿。"),
    "single-ink": ("单页竖排", "单线墨框、九栏二十字，不设版心，适合单页书稿。"),
    "blue-manuscript": ("单页竖排", "蓝色细栏、宽松字格，适合抄录与阅读笔记。"),
    "warm-edition": ("古籍双面", "米色纸面、褐色双框与复线鱼尾，适合刻本风格。"),
    "large-print": ("单页竖排", "大纸大字、少栏疏排，适合放大阅读和短文。"),
    "pocket-book": ("单页竖排", "小开本、紧凑字格与单线框，适合便携短册。"),
    "annotation-page": (
        "单页竖排",
        "加大上方留白、减少栏数，为眉批与栏间注文预留空间。",
    ),
    "colophon-page": ("单页竖排", "无界栏、宽留白，适合序跋、题记与落款。"),
    "sutra-page": ("单页竖排", "横长纸张、二十四栏三十字，适合经文连续长行。"),
    "horizontal-study": ("横排阅读", "单栏横排配浅色行线，适合研读、课堂整理与注解。"),
    "horizontal-columns": (
        "横排阅读",
        "横向纸张分成两栏，适合横排短文集和篇幅较长的正文。",
    ),
}


def page_style_sample(key):
    """Independent sample content for previews and reproducible export checks."""
    from .model import Book, Block, Inline

    name, profile = page_style_presets()[key]
    return Book(
        name,
        (
            Block((Inline("读书小记"),), kind="heading"),
            Block(
                (
                    Inline(
                        "山窗日暖，竹影入帘。展卷读书，心与古人相接。晨起看山，夜深听雨。读书贵在明理，作文重在达意。细读而深思，温故而知新。"
                    ),
                )
            ),
            Block((Inline("小注：此段从景物引入读书之乐。"),), kind="commentary"),
            Block((Inline("学而时习之，不亦说乎？有朋自远方来，不亦乐乎？"),)),
        ),
        volume="卷一",
        author="竹简书屋",
        profile=profile,
    )
