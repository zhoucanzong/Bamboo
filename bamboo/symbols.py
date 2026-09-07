"""Font-independent vector ornaments; IDs are not private-use Unicode points."""

from .model import Line, Polygon, BambooError

STYLES = {
    "solid": "实心鱼尾",
    "outline": "空心鱼尾",
    "double": "双线鱼尾",
    "notched": "凹口鱼尾",
    "split": "分瓣鱼尾",
    "stepped": "阶形鱼尾",
}
DIRECTIONS = {"down": "下", "up": "上", "left": "左", "right": "右"}


def fish_tail(style, direction, cx, cy, size, color):
    if style not in STYLES or direction not in DIRECTIONS:
        raise BambooError("未知鱼尾符号")

    def transform(point):
        x, y = point
        if direction == "up":
            x, y = -x, -y
        elif direction == "left":
            x, y = -y, x
        elif direction == "right":
            x, y = y, -x
        return cx + x * size, cy + y * size

    lines, polygons = [], []
    outline = [(-0.5, -0.35), (0.5, -0.35), (0, 0.35), (-0.5, -0.35)]
    if style in {"outline", "double"}:
        for scale in ([1, 0.68] if style == "double" else [1]):
            points = [transform((x * scale, y * scale)) for x, y in outline]
            lines.extend(
                Line(*a, *b, max(0.6, size * 0.035), color)
                for a, b in zip(points, points[1:])
            )
    else:
        paths = {
            "solid": [outline[:-1]],
            "notched": [
                [
                    (-0.5, -0.35),
                    (-0.16, -0.35),
                    (0, -0.12),
                    (0.16, -0.35),
                    (0.5, -0.35),
                    (0, 0.35),
                ]
            ],
            "split": [
                [(-0.5, -0.35), (-0.05, -0.35), (-0.05, 0.25)],
                [(0.05, -0.35), (0.5, -0.35), (0.05, 0.25)],
            ],
            "stepped": [
                [
                    (-0.5, -0.35),
                    (0.5, -0.35),
                    (0.5, -0.1),
                    (0.27, -0.1),
                    (0.27, 0.12),
                    (0, 0.35),
                    (-0.27, 0.12),
                    (-0.27, -0.1),
                    (-0.5, -0.1),
                ]
            ],
        }
        polygons = [
            Polygon(tuple(transform(point) for point in path), color)
            for path in paths[style]
        ]
    return lines, polygons
