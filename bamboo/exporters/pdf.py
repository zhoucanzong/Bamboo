"""Selectable vector PDF with embedded CJK font and page bookmarks."""

import fitz


def rgb(value):
    return tuple(int(value[i : i + 2], 16) / 255 for i in (1, 3, 5))


def pdf_document(layout, font):
    doc = fitz.open()
    profile = layout.book.profile
    toc, heading_seen = [], set()
    for leaf in layout.pages:
        page = doc.new_page(width=profile.width, height=profile.height)
        page.draw_rect(page.rect, color=None, fill=rgb(profile.paper))
        page.insert_font(fontname="Bamboo", fontbuffer=font.data)
        for line in leaf.lines:
            page.draw_line(
                (line.x1, line.y1),
                (line.x2, line.y2),
                color=rgb(line.color),
                width=line.width,
            )
        for polygon in leaf.polygons:
            shape = page.new_shape()
            shape.draw_polyline(polygon.points)
            shape.finish(color=None, fill=rgb(polygon.color), closePath=True)
            shape.commit()
        for glyph in leaf.glyphs:
            page.insert_text(
                font.origin(glyph),
                glyph.text,
                fontname="Bamboo",
                fontsize=glyph.size,
                color=rgb(glyph.color),
            )
            if glyph.role == "heading" and glyph.block not in heading_seen:
                heading_seen.add(glyph.block)
                toc.append([1, layout.book.blocks[glyph.block].text, leaf.number])
    if toc:
        doc.set_toc(toc)
    doc.set_metadata(
        {
            "title": layout.book.title,
            "author": layout.book.author,
            "subject": layout.book.volume,
            "creator": "Bamboo",
            "producer": "Bamboo typesetting engine",
        }
    )
    return doc


def export_pdf(layout, font, path):
    with pdf_document(layout, font) as doc:
        doc.save(str(path), garbage=4, deflate=True)
