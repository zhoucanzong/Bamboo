"""Portable, offline SVG book reader with embedded font and semantic transcript."""

from base64 import b64encode
from html import escape


def export_html(layout, font, path):
    profile = layout.book.profile
    pages = []
    page_styles = []
    for page in layout.pages:
        page_profile = page.profile or profile
        page_styles.append(
            f"@page leaf{page.number}{{size:{page_profile.width}pt {page_profile.height}pt;margin:0}}"
        )
        parts = [
            f'<svg viewBox="0 0 {page_profile.width} {page_profile.height}" xmlns="http://www.w3.org/2000/svg" '
            f'role="img" aria-label="{escape(layout.book.title, quote=True)} 第 {page.number} 葉">',
            f'<rect width="{page_profile.width}" height="{page_profile.height}" fill="{page_profile.paper}"/>',
        ]
        for line in page.lines:
            parts.append(
                f'<line x1="{line.x1:.5f}" y1="{line.y1:.5f}" x2="{line.x2:.5f}" '
                f'y2="{line.y2:.5f}" stroke="{line.color}" stroke-width="{line.width}"/>'
            )
        for polygon in page.polygons:
            points = " ".join(f"{x:.5f},{y:.5f}" for x, y in polygon.points)
            parts.append(f'<polygon points="{points}" fill="{polygon.color}"/>')
        for glyph in page.glyphs:
            x, y = font.origin(glyph)
            bold = (
                f' stroke="{glyph.color}" stroke-width="{glyph.size*.022}" paint-order="stroke"'
                if glyph.bold
                else ""
            )
            parts.append(
                f'<text x="{x:.5f}" y="{y:.5f}" font-size="{glyph.size}" fill="{glyph.color}" '
                f'data-source="{glyph.block}:{glyph.inline}:{glyph.offset}"{bold}>{escape(glyph.text)}</text>'
            )
        parts.append("</svg>")
        pages.append(
            f'<section class="leaf" id="leaf-{page.number}" style="page:leaf{page.number};--print-width:{page_profile.width}pt;--print-height:{page_profile.height}pt" aria-label="第 {page.number} 葉">'
            + "".join(parts)
            + "</section>"
        )
    transcript = []
    if layout.book.special is not None:
        for page in layout.pages:
            for widget in page.widgets:
                if widget["kind"] == "table":
                    transcript.append("<table>")
                    for row in range(widget["rows"]):
                        transcript.append(
                            "<tr>"
                            + "".join(
                                "<td>" + escape(c["text"]) + "</td>"
                                for c in widget["cells"]
                                if c["row"] == row
                            )
                            + "</tr>"
                        )
                    transcript.append("</table>")
                else:
                    transcript.append("<p>" + escape(widget["text"]) + "</p>")
    note_index = 0
    for block in layout.book.blocks:
        if block.kind == "pagebreak":
            transcript.append('<hr aria-label="换页">')
            continue
        tag = "h2" if block.kind == "heading" else "p"
        spans = []
        numbered = []
        for inline in block.inlines:
            value = escape(inline.text)
            if inline.kind == "numbered_note":
                from ..layout import chinese_number

                note_index += 1
                marker = f"【{chinese_number(note_index)}】"
                spans.append(f'<a href="#note-{inline.target}">{marker}</a>')
                label = (
                    f'<span class="note-label{ " boxed" if inline.boxed else ""}">{escape(inline.annotation)}</span>'
                    if inline.annotation
                    else ""
                )
                numbered.append(
                    f'<p id="note-{inline.target}" class="numbered-note">{marker}{label}{value}</p>'
                )
                continue
            if inline.kind == "label":
                spans.append(
                    f'<span class="note-label{ " boxed" if inline.boxed else ""}">{value}</span>'
                )
                continue
            spans.append(
                f"<ruby>{value}<rt>{escape(inline.annotation)}</rt></ruby>"
                if inline.kind == "ruby"
                else (
                    f"<small>〔{value}〕</small>"
                    if inline.kind in {"note", "footnote"}
                    else f"<em>{value}</em>" if inline.kind == "emphasis" else value
                )
            )
        transcript.append(f'<{tag}>{"".join(spans)}</{tag}>')
        transcript.extend(numbered)
    for note in layout.book.annotations:
        transcript.append(
            f'<aside><small>{"眉批" if note.placement=="top" else "旁批"}：{escape(note.text)}</small></aside>'
        )
    css = f"""
@font-face{{font-family:BambooPage;src:url(data:{font.mime};base64,{b64encode(font.data).decode()})}}
:root{{--leaf-width:{profile.width}px;color-scheme:light}}
*{{box-sizing:border-box}}body{{margin:0;background:#e8e5df;color:#282824;font:14px system-ui,sans-serif}}
header{{position:sticky;top:0;z-index:2;background:#f9f8f2f5;border-bottom:1px solid #d0cbbf;backdrop-filter:blur(10px)}}
.toolbar{{max-width:1180px;margin:auto;display:flex;align-items:center;gap:18px;padding:14px 24px;flex-wrap:wrap}}
.brand{{font-size:12px;letter-spacing:.24em;color:#426154}}h1{{font-size:18px;font-weight:500;margin:0 auto 0 0}}
button,select{{font:inherit;background:#fffdf6;border:1px solid #c7c2b6;border-radius:4px;padding:7px 10px;color:inherit}}
button{{cursor:pointer}}button:disabled{{opacity:.4;cursor:default}}button:focus-visible,select:focus-visible{{outline:2px solid #557766}}
main{{padding:36px 24px;overflow-x:auto}}.leaf{{width:var(--leaf-width);max-width:none;margin:0 auto 32px;box-shadow:0 4px 24px #332c2120}}
svg{{display:block;width:100%;height:auto}}svg text{{font-family:BambooPage;white-space:pre}}
.leaf.active{{outline:2px solid #65846c;outline-offset:5px}}.hint{{text-align:center;color:#67665d;margin:0 0 26px;font-size:12px}}
details{{max-width:842px;margin:0 auto 48px;padding:20px 26px;background:#faf9f4;line-height:1.9}}
.note-label{{font-size:.8em;margin:0 .3em;padding:.1em .2em}}.note-label.boxed{{border:1px solid currentColor}}.numbered-note{{font-size:.85em}}
summary{{cursor:pointer}}details h2{{font-size:18px}}small{{color:#6b675e}}em{{color:#9b3028;font-style:normal}}
@media(max-width:900px){{:root{{--leaf-width:calc(100vw - 32px)}}main{{padding:24px 16px}}.toolbar{{padding:12px 16px;gap:10px}}}}
@page{{size:{profile.width}pt {profile.height}pt;margin:0}}
@media print{{body{{background:white}}header,.hint,details{{display:none}}main{{padding:0;overflow:visible}}.leaf{{width:var(--print-width);height:var(--print-height);margin:0;box-shadow:none;break-after:page}}.leaf:last-child{{break-after:auto}}.leaf.active{{outline:none}}}}
"""
    css += "\n".join(page_styles)
    js = """
const leaves=[...document.querySelectorAll('.leaf')], picker=document.querySelector('#page');
let current=0;
function activate(i,scroll){current=Math.max(0,Math.min(leaves.length-1,i));picker.value=String(current);
 leaves.forEach((p,n)=>p.classList.toggle('active',n===current));
 document.querySelector('#prev').disabled=current===0;document.querySelector('#next').disabled=current===leaves.length-1;
 if(scroll)leaves[current].scrollIntoView({behavior:'smooth',block:'center'});}
picker.addEventListener('change',()=>activate(Number(picker.value),true));
document.querySelector('#prev').addEventListener('click',()=>activate(current-1,true));
document.querySelector('#next').addEventListener('click',()=>activate(current+1,true));
document.querySelector('#zoom').addEventListener('change',e=>{
 document.documentElement.style.setProperty('--leaf-width',e.target.value==='fit'?'min(100vw - 48px, 1180px)':e.target.value+'px');});
document.querySelector('#print').addEventListener('click',()=>window.print());
document.addEventListener('keydown',e=>{if(/INPUT|SELECT|TEXTAREA/.test(e.target.tagName))return;
 if(e.key==='ArrowLeft'){e.preventDefault();activate(current+(rtl?1:-1),true)}
 if(e.key==='ArrowRight'){e.preventDefault();activate(current+(rtl?-1:1),true)}});
activate(0,false);
"""
    js = ("const rtl=true;\n" if profile.vertical else "const rtl=false;\n") + js
    options = "".join(
        f'<option value="{i}">第 {i+1} 葉 / {len(pages)}</option>'
        for i in range(len(pages))
    )
    title = escape(layout.book.title)
    html = f"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="generator" content="Bamboo"><title>{title} · Bamboo</title><style>{css}</style></head>
<body><header><div class="toolbar"><span class="brand">BAMBOO / 简牍</span><h1>{title}</h1>
<button id="prev" aria-label="上一葉">{"上一葉 →" if profile.vertical else "← 上一頁"}</button><select id="page" aria-label="选择书叶">{options}</select>
<button id="next" aria-label="下一葉">{"← 下一葉" if profile.vertical else "下一頁 →"}</button>
<select id="zoom" aria-label="缩放"><option value="{profile.width}">原始比例</option><option value="fit">适应窗口</option>
<option value="{profile.width*1.5}">150%</option></select><button id="print">打印</button></div></header>
<main><p class="hint">{escape(layout.book.volume)} · {"自右向左閱讀" if profile.vertical else "自左向右閱讀"} · 使用 ← → 翻葉</p>{''.join(pages)}</main>
<details><summary>查看可复制的原文与夹注</summary>{''.join(transcript)}</details><script>{js}</script></body></html>"""
    path.write_text(html, encoding="utf-8")
