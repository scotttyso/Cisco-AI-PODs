#!/usr/bin/env python3
"""Generate the UCS C880 M8 deployment chapter workflow figures as SVG and PNG.

Layout mirrors the Cisco CVD 6.00-inch text column standard.
This generator creates the files consumed by MOP-06-ucs-c880-deploy.md.
"""

from __future__ import annotations

import html
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent

FIG_W = 600
MARGIN = 10
COLS = 4
COL_GAP = 18
ROW_GAP = 22
CONNECTOR_R = 9
CONNECTOR_GAP = COL_GAP
GUTTER = CONNECTOR_R * 2 + CONNECTOR_GAP
PAD_X = 6
PAD_Y = 5
STROKE = 0.8
BODY_PT = 7.4
FONT = round(BODY_PT / 72 * 100, 2)
HEADER_FONT = round(FONT * 0.92, 2)
LINE_H = round(FONT * 1.22, 2)
BOX_W = (FIG_W - MARGIN * 2 - GUTTER * 2 - (COLS - 1) * COL_GAP) // COLS
TEXT_W = BOX_W - PAD_X * 2
START_W_RATIO = 0.82
START_H_LINES = 1.5
TERM_PAD_X = PAD_X * 3

FONT_FAMILY = "system-ui, -apple-system, Segoe UI, sans-serif"
METRIC_FONT = "/System/Library/Fonts/Helvetica.ttc"

NAVY = "#07182D"
BLUE = "#0A60FF"
BLUE_TINT = "#EDF3FE"
WHITE = "#FFFFFF"
LT2_BORDER = "#B4B9C0"
GRAY_DARK = "#525E6C"

OVERVIEW = [
    [
        {"lines": ["Start"], "kind": "terminator"},
        {"header": "Procedure 1", "lines": ["Hostname, DNS,", "and NTP"]},
        {"header": "Procedure 2", "lines": ["Serial over LAN", "& vKVM access"]},
        {"header": "Procedure 3", "lines": ["Health checks &", "HW inventory"]},
    ],
    [
        {"header": "Procedure 4", "lines": ["Upgrade script:", "BMC, BIOS, ERoT"]},
        {"header": "Procedure 5", "lines": ["HUU ISO: host", "adapters & RAID"]},
        {"header": "Procedure 6", "lines": ["Host BIOS &", "NIC modes"]},
        {"lines": ["C880 ready for", "OS deployment"], "kind": "terminator"},
    ],
]


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def measure(text: str, bold: bool) -> float:
    font = ImageFont.truetype(METRIC_FONT, 100, index=1 if bold else 0)
    return font.getlength(text) / 100


def terminator_size(node: dict) -> tuple[float, float]:
    """Compact stadium size for overview start/end ovals."""
    label_w = max(measure(line, False) * FONT for line in node["lines"])
    width = min(BOX_W, max(round(BOX_W * START_W_RATIO), round(label_w + TERM_PAD_X * 2)))
    height = round(PAD_Y * 2 + LINE_H * max(len(node["lines"]), START_H_LINES))
    return width, height


def check_labels_fit(figures: list[list[list[dict]]]) -> None:
    for rows in figures:
        for row in rows:
            for node in row:
                for line in node["lines"]:
                    if measure(line, False) * FONT > TEXT_W:
                        raise ValueError(f"body label overflows: {line!r}")
                header = node.get("header")
                if header and measure(header, True) * HEADER_FONT > TEXT_W:
                    raise ValueError(f"header overflows: {header!r}")


def marker(marker_id: str) -> str:
    return (
        f'<defs><marker id="{marker_id}" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{GRAY_DARK}"/></marker></defs>'
    )


def arrow(x1: float, y1: float, x2: float, y2: float, marker_id: str) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{GRAY_DARK}" '
        f'stroke-width="{STROKE}" marker-end="url(#{marker_id})"/>'
    )


def connector(cx: float, cy: float, tag: str) -> str:
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{CONNECTOR_R}" fill="{WHITE}" '
        f'stroke="{BLUE}" stroke-width="{STROKE * 1.2}"/>'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" dominant-baseline="middle" '
        f'fill="{BLUE}" font-size="{FONT}" font-weight="700" '
        f'font-family="{FONT_FAMILY}">{tag}</text>'
    )


def box_height(rows: list[list[dict]]) -> float:
    blocks = max(
        len(node["lines"]) + (1 if node.get("header") else 0)
        for row in rows
        for node in row
    )
    return PAD_Y * 2 + blocks * LINE_H


def box(x: float, y: float, w: float, h: float, node: dict) -> str:
    kind = node.get("kind", "step")
    terminal = kind in ("terminal", "terminator")
    fill = BLUE_TINT if terminal else WHITE
    stroke = BLUE if terminal else LT2_BORDER
    rx = h / 2 if kind == "terminator" else 2
    cx = x + w / 2
    header = node.get("header")
    header_h = LINE_H if header else 0
    block_h = header_h + len(node["lines"]) * LINE_H
    top = y + h / 2 - block_h / 2 + LINE_H / 2

    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" ry="{rx}" '
        f'fill="{fill}" stroke="{stroke}" stroke-width="{STROKE}"/>'
    ]
    if header:
        parts.append(
            f'<text x="{cx}" y="{top}" text-anchor="middle" dominant-baseline="middle" '
            f'fill="{BLUE}" font-size="{HEADER_FONT}" font-weight="700" '
            f'font-family="{FONT_FAMILY}">{esc(header)}</text>'
        )
    spans = "".join(
        f'<tspan x="{cx}" dy="{0 if index == 0 else LINE_H}">{esc(line)}</tspan>'
        for index, line in enumerate(node["lines"])
    )
    parts.append(
        f'<text x="{cx}" y="{top + header_h}" text-anchor="middle" '
        f'dominant-baseline="middle" fill="{NAVY}" font-size="{FONT}" '
        f'font-family="{FONT_FAMILY}">{spans}</text>'
    )
    return "".join(parts)


def wrapped_figure(rows: list[list[dict]]) -> tuple[str, int, int]:
    box_h = box_height(rows)
    fig_h = round(MARGIN * 2 + len(rows) * box_h + (len(rows) - 1) * ROW_GAP)
    x0 = MARGIN + GUTTER
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{FIG_W}" height="{fig_h}" '
        f'viewBox="0 0 {FIG_W} {fig_h}">',
        f'<rect width="{FIG_W}" height="{fig_h}" fill="{WHITE}"/>',
        marker("flow"),
    ]

    for row_index, row in enumerate(rows):
        y = MARGIN + row_index * (box_h + ROW_GAP)
        mid_y = y + box_h / 2
        row_right = x0 + len(row) * BOX_W + (len(row) - 1) * COL_GAP
        if row_index:
            parts.append(connector(MARGIN + CONNECTOR_R, mid_y, "A"))
            parts.append(arrow(MARGIN + 2 * CONNECTOR_R, mid_y, x0 - 2, mid_y, "flow"))
        for column_index, node in enumerate(row):
            x = x0 + column_index * (BOX_W + COL_GAP)
            if node.get("kind") == "terminator" and not node.get("header"):
                node_w, node_h = terminator_size(node)
                node_x = x + (BOX_W - node_w) / 2
                node_y = y + (box_h - node_h) / 2
            else:
                node_w, node_h = BOX_W, box_h
                node_x, node_y = x, y
            parts.append(box(node_x, node_y, node_w, node_h, node))
            if column_index < len(row) - 1:
                parts.append(
                    arrow(
                        node_x + node_w,
                        mid_y,
                        x + BOX_W + COL_GAP - 2,
                        mid_y,
                        "flow",
                    )
                )
        if row_index < len(rows) - 1:
            parts.append(
                arrow(row_right, mid_y, row_right + CONNECTOR_GAP - 2, mid_y, "flow")
            )
            parts.append(
                connector(row_right + CONNECTOR_GAP + CONNECTOR_R, mid_y, "A")
            )
    parts.append("</svg>")
    return "".join(parts), fig_h, FIG_W


def find_chrome() -> Path | None:
    cache = Path.home() / ".cache/puppeteer"
    if cache.is_dir():
        for candidate in sorted(cache.rglob("chrome-headless-shell")):
            if candidate.is_file():
                return candidate
    for name in ("chromium", "google-chrome"):
        found = shutil.which(name)
        if found:
            return Path(found)
    for app in ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]:
        if Path(app).is_file():
            return Path(app)
    return None


def rasterize(svg_path: Path, png_path: Path, width: int, height: int) -> bool:
    chrome = find_chrome()
    if chrome is None:
        print(f"WARNING: no Chromium found; {png_path.name} not regenerated", file=sys.stderr)
        return False
    html_path = svg_path.with_suffix(".html")
    html_path.write_text(
        f'<html><body style="margin:0">{svg_path.read_text(encoding="utf-8")}</body></html>',
        encoding="utf-8",
    )
    try:
        subprocess.run(
            [
                str(chrome),
                "--headless",
                "--disable-gpu",
                f"--screenshot={png_path}",
                f"--window-size={width},{height}",
                "--force-device-scale-factor=4",
                "--default-background-color=FFFFFFFF",
                html_path.as_uri(),
            ],
            check=True,
            capture_output=True,
        )
    finally:
        html_path.unlink(missing_ok=True)
    return png_path.exists()


def main() -> int:
    check_labels_fit([OVERVIEW])
    figures = [
        ("ucs-c880-deployment-workflow", wrapped_figure(OVERVIEW)),
    ]
    for name, (svg, height, width) in figures:
        svg_path = OUT_DIR / f"{name}.svg"
        png_path = OUT_DIR / f"{name}.png"
        svg_path.write_text(svg, encoding="utf-8")
        ok = rasterize(svg_path, png_path, width, height)
        print(
            f"{name}: {width}x{height} svg ok, "
            f"{'png ok' if ok else 'png SKIPPED'}, embed at 6.00in"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
