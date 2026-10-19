#!/usr/bin/env python3
"""Generate the ND chapter flow figures as SVG, then rasterize to PNG.

Replaces the mermaid fences that previously lived in MOP-ND4-install.md.
Mermaid laid these out vertically, which cost most of a page per drill-down;
these figures wrap into even rows joined by lettered connector circles.

Drawing scale
-------------
The SVG user unit is 1/100 inch at the width the chapter embeds the figure,
so a length in these constants is directly readable as hundredths of an inch
on the printed page and the font size falls out as a real point size rather
than something to be discovered after the render.

Body text is pinned to `BODY_PT` and every figure uses it, so resizing a
figure changes how much page it takes rather than how big its labels read.
`check_labels_fit` measures each label against the box interior and warns when
one has outgrown it, since a pinned size cannot absorb a longer label.

Layout mirrors the canvas at
  ~/.cursor/projects/<workspace>/canvases/CVD-AIPOD-nd-cluster-deploy-figures.canvas.tsx
Keep the two in step: the canvas is where layout is iterated, this script is
what the chapter build consumes.

Usage:
    python3 01-nd-cluster/docs/workflows/scripts/build_workflow_figures.py
"""

from __future__ import annotations

import html
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import ImageFont

OUT_DIR = Path(__file__).resolve().parent.parent

# Width the full-bleed chapter figures embed at, matching the screenshots.
CHAPTER_FIG_IN = 6.0
UNITS_PER_IN = 100
FIG_W = int(CHAPTER_FIG_IN * UNITS_PER_IN)

COLS = 4
MARGIN = 10
# The widest gap the four-column rows tolerate: anything more shrinks the boxes
# past the longest body label at the pinned font, which the overflow check below
# reports. Figure 1 has three columns and derives its own, wider, gap.
COL_GAP = 18
ROW_GAP = 22
CONNECTOR_R = 9
# Equal to COL_GAP so the arrows into and out of a connector circle are the
# same length as the arrows between boxes.
CONNECTOR_GAP = COL_GAP
GUTTER = CONNECTOR_R * 2 + CONNECTOR_GAP
PAD_X = 6
PAD_Y = 5
STROKE = 0.8
LINE_RATIO = 1.22
HEADER_RATIO = 0.92
# Locked 2026-09-22: 7.4pt body, header = BODY_PT * HEADER_RATIO (6.8pt).
# Do not retune for a narrower figure — reword the overflowing label instead.
BODY_PT = 7.4

# Every box in every chapter figure is this wide, so the figures share one
# drawing scale and their labels render at the same point size in Word.
BOX_W = (FIG_W - MARGIN * 2 - GUTTER * 2 - (COLS - 1) * COL_GAP) // COLS
TEXT_W = BOX_W - PAD_X * 2
# Overview (figure 1) start/end ovals: stadiums, centred in the column, smaller
# than a step box. Width is START_W_RATIO of BOX_W, grown to the label. Height
# follows line count. Procedure figures keep a rectangular Verify terminal.
START_W_RATIO = 0.82
START_H_LINES = 1.5
# Ovals carry more side padding than a step box so the stadium curve does not
# crowd the label.
TERM_PAD_X = PAD_X * 3
DECISION_TEXT_OFFSET_Y = 3

FONT_FAMILY = "system-ui, -apple-system, Segoe UI, sans-serif"
# Measured with Helvetica, which is wider than the SF/system-ui the browser
# actually renders. Fitting against the wider face keeps the real render
# inside the box rather than one rounding error outside it.
_METRIC_FONT = "/System/Library/Fonts/Helvetica.ttc"

NAVY = "#07182D"
BLUE = "#0A60FF"
BLUE_TINT = "#EDF3FE"
WHITE = "#FFFFFF"
LT2_BORDER = "#B4B9C0"
GRAY_DARK = "#525E6C"
# Locked 2026-09-22 for decision symbols only. accent6 in the chapter Word
# theme; see docs/build/brand_template.py.
AMBER = "#E07B00"
AMBER_TINT = "#FDF3E7"


def esc(text: str) -> str:
    return html.escape(text, quote=False)


def _measure(text: str, bold: bool) -> float:
    """Width of `text` per 1 unit of font size."""
    font = ImageFont.truetype(_METRIC_FONT, 100, index=1 if bold else 0)
    return font.getlength(text) / 100


def terminator_size(node: dict) -> tuple[float, float]:
    """Compact stadium size for overview start/end ovals."""
    label_w = max(_measure(line, False) * FONT for line in node["lines"])
    width = min(BOX_W, max(round(BOX_W * START_W_RATIO), round(label_w + TERM_PAD_X * 2)))
    height = round(PAD_Y * 2 + LINE_H * max(len(node["lines"]), START_H_LINES))
    return width, height


def check_labels_fit(figures: list[list[list[dict]]]) -> None:
    """Warn for any label too wide for a box interior at the pinned font size.

    The font is pinned rather than maximized, so a label that outgrows its box
    has to be reworded. Without this check the overflow only shows up in the
    render, by which point the figure is already in the chapter.
    """
    for rows in figures:
        for row in rows:
            for node in row:
                for line in node["lines"]:
                    if _measure(line, False) * FONT > TEXT_W:
                        print(f"WARNING: body label overflows its box: {line!r}", file=sys.stderr)
                if node.get("header") and _measure(node["header"], True) * HEADER_FONT > TEXT_W:
                    print(f"WARNING: header overflows its box: {node['header']!r}", file=sys.stderr)


def marker(mid: str) -> str:
    return (
        f'<defs><marker id="{mid}" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="5" markerHeight="5" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{GRAY_DARK}"/></marker></defs>'
    )


def arrow(x1: float, y1: float, x2: float, y2: float, mid: str) -> str:
    return (
        f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{GRAY_DARK}" '
        f'stroke-width="{STROKE}" marker-end="url(#{mid})"/>'
    )


def box(x: float, y: float, w: float, h: float, node: dict) -> str:
    kind = node.get("kind", "step")
    # "terminator" is the flowchart start/end symbol and draws as a stadium;
    # "terminal" ends a procedure figure and stays a tinted rectangle.
    if kind in ("terminal", "terminator"):
        fill, stroke, head = BLUE_TINT, BLUE, BLUE
    else:
        fill, stroke, head = WHITE, LT2_BORDER, BLUE
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
            f'fill="{head}" font-size="{HEADER_FONT}" font-weight="700" '
            f'font-family="{FONT_FAMILY}">{esc(header)}</text>'
        )
    spans = "".join(
        f'<tspan x="{cx}" dy="{0 if i == 0 else LINE_H}">{esc(line)}</tspan>'
        for i, line in enumerate(node["lines"])
    )
    parts.append(
        f'<text x="{cx}" y="{top + header_h}" text-anchor="middle" '
        f'dominant-baseline="middle" fill="{NAVY}" font-size="{FONT}" '
        f'font-family="{FONT_FAMILY}">{spans}</text>'
    )
    return "".join(parts)


def connector(cx: float, cy: float, tag: str) -> str:
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{CONNECTOR_R}" fill="{WHITE}" '
        f'stroke="{BLUE}" stroke-width="{STROKE * 1.2}"/>'
        f'<text x="{cx}" y="{cy}" text-anchor="middle" '
        f'dominant-baseline="middle" fill="{BLUE}" font-size="{FONT}" '
        f'font-weight="700" font-family="{FONT_FAMILY}">{tag}</text>'
    )


def box_height(rows: list[list[dict]]) -> float:
    blocks = max(len(n["lines"]) + (1 if n.get("header") else 0) for r in rows for n in r)
    return PAD_Y * 2 + blocks * LINE_H


def wrapped_figure(rows: list[list[dict]]) -> tuple[str, int, int]:
    """Even rows of equal-width boxes, joined row to row by lettered circles.

    A connector gutter is reserved on both sides of every row, including the
    first and last where only one circle is drawn, so box geometry is identical
    on every row.
    """
    box_h = box_height(rows)
    fig_h = round(MARGIN * 2 + len(rows) * box_h + (len(rows) - 1) * ROW_GAP)

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{FIG_W}" height="{fig_h}" '
        f'viewBox="0 0 {FIG_W} {fig_h}">',
        f'<rect width="{FIG_W}" height="{fig_h}" fill="{WHITE}"/>',
        marker("a"),
    ]

    x0 = MARGIN + GUTTER
    for row_idx, row in enumerate(rows):
        y = MARGIN + row_idx * (box_h + ROW_GAP)
        mid_y = y + box_h / 2
        row_right = x0 + len(row) * BOX_W + (len(row) - 1) * COL_GAP

        if row_idx > 0:
            out.append(connector(MARGIN + CONNECTOR_R, mid_y, chr(64 + row_idx)))
            out.append(arrow(MARGIN + 2 * CONNECTOR_R, mid_y, x0 - 2, mid_y, "a"))

        for col_idx, node in enumerate(row):
            x = x0 + col_idx * (BOX_W + COL_GAP)
            out.append(box(x, y, BOX_W, box_h, node))
            if col_idx < len(row) - 1:
                out.append(arrow(x + BOX_W, mid_y, x + BOX_W + COL_GAP - 2, mid_y, "a"))

        if row_idx < len(rows) - 1:
            out.append(arrow(row_right, mid_y, row_right + CONNECTOR_GAP - 2, mid_y, "a"))
            out.append(
                connector(row_right + CONNECTOR_GAP + CONNECTOR_R, mid_y, chr(65 + row_idx))
            )

    out.append("</svg>")
    return "".join(out), fig_h, FIG_W


def overview_figure() -> tuple[str, int, int]:
    """Chapter workflow: the linear run on row one, the whole branch on row two.

    Both rows carry three columns, so they start and end on the same x. The
    diamond opens row two and the two outcomes stack beside it, one above the
    other, so the Yes leg leaves the top vertex and the No leg the bottom one.
    Procedure 3 is the single exit either way.
    """
    box_h = box_height([OVERVIEW_ROW1, OVERVIEW_PAIR + [OVERVIEW_END]])

    # This figure carries three columns where the procedure figures carry four,
    # so at the shared column gap it would embed a third narrower than they do.
    # Boxes keep the common width — that is what pins the text size — and the
    # spare width goes into the gaps instead, which is also what gives the
    # branch legs room to run.
    gap = (FIG_W - MARGIN * 2 - CONNECTOR_R * 4 - 3 * BOX_W) // 4
    gutter = CONNECTOR_R * 2 + gap
    run = gap - 2

    x0 = MARGIN + gutter
    def slot(i: int) -> float:
        return x0 + i * (BOX_W + gap)

    row1_y = MARGIN
    row1_mid = row1_y + box_h / 2
    row1_right = slot(2) + BOX_W
    start_w, start_h = terminator_size(OVERVIEW_ROW1[0])
    start_x = slot(0) + (BOX_W - start_w) / 2
    start_y = row1_y + (box_h - start_h) / 2
    fig_w = round(row1_right + gap + CONNECTOR_R * 2 + MARGIN)

    # Column 0 of row 2 holds the diamond, column 1 the two stacked outcomes,
    # column 2 the end state on the lower line.
    d_left, d_right = slot(0), slot(0) + BOX_W
    d_cx = d_left + BOX_W / 2
    stack_x, end_x = slot(1), slot(2)
    stack_cx = stack_x + BOX_W / 2
    diamond_h = 5 * LINE_H
    # Each leg leaves a vertex of the diamond, so the box it feeds has to sit
    # beyond that vertex — otherwise the leg would double back over the shape it
    # just left. This gap puts each box's centre line `jog` past the vertex.
    jog = LINE_H / 2
    sub_gap = round(diamond_h - box_h + 2 * jog)

    p2_y = round(row1_y + box_h + ROW_GAP, 2)
    p3_y = round(p2_y + box_h + sub_gap, 2)
    p2_mid = p2_y + box_h / 2
    p3_mid = p3_y + box_h / 2
    end_w, end_h = terminator_size(OVERVIEW_END)
    end_box_x = end_x + (BOX_W - end_w) / 2
    end_box_y = p3_y + (box_h - end_h) / 2
    # The diamond centres on the gap between the two boxes, so its upper and
    # lower slopes sit level with them and the two legs mirror each other.
    stack_mid = p2_y + box_h + sub_gap / 2
    a_cx = x0 - gap - CONNECTOR_R
    fig_h = round(p3_y + box_h + MARGIN)

    # The diamond keeps the column width so the row stays on one pitch, which
    # leaves less room for text than a rectangle: at the two text lines the
    # taper has already eaten the outer fifth of the width.
    usable = BOX_W * (1 - LINE_H / diamond_h) - PAD_X * 2
    for line in DECISION_LINES:
        if _measure(line, False) * FONT > usable:
            print(
                f"WARNING: decision text is too wide for the diamond: {line!r}",
                file=sys.stderr,
            )

    def label(x: float, y: float, text: str) -> str:
        return (
            f'<text x="{x}" y="{y}" text-anchor="middle" fill="{GRAY_DARK}" '
            f'font-size="{HEADER_FONT}" font-weight="600" '
            f'font-family="{FONT_FAMILY}">{text}</text>'
        )

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{fig_w}" height="{fig_h}" '
        f'viewBox="0 0 {fig_w} {fig_h}">',
        f'<rect width="{fig_w}" height="{fig_h}" fill="{WHITE}"/>',
        marker("b"),
    ]
    out.append(box(start_x, start_y, start_w, start_h, OVERVIEW_ROW1[0]))
    out.append(arrow(start_x + start_w, row1_mid, slot(1) - 2, row1_mid, "b"))
    for i, node in enumerate(OVERVIEW_ROW1[1:], start=1):
        out.append(box(slot(i), row1_y, BOX_W, box_h, node))
        if i < len(OVERVIEW_ROW1) - 1:
            out.append(arrow(slot(i) + BOX_W, row1_mid, slot(i + 1) - 2, row1_mid, "b"))
    out.append(arrow(row1_right, row1_mid, row1_right + run, row1_mid, "b"))
    out.append(connector(row1_right + gap + CONNECTOR_R, row1_mid, "A"))

    out.append(connector(a_cx, stack_mid, "A"))
    out.append(arrow(a_cx + CONNECTOR_R, stack_mid, d_left - 2, stack_mid, "b"))

    # Amber sets the branch apart from the steps either side of it. It is the
    # only decision in the figure set, so the colour carries meaning rather
    # than decoration.
    out.append(
        f'<polygon points="{d_cx},{stack_mid - diamond_h / 2} {d_right},{stack_mid} '
        f'{d_cx},{stack_mid + diamond_h / 2} {d_left},{stack_mid}" '
        f'fill="{AMBER_TINT}" stroke="{AMBER}" stroke-width="{STROKE}"/>'
    )
    spans = "".join(
        f'<tspan x="{d_cx}" dy="{0 if i == 0 else LINE_H}">{esc(line)}</tspan>'
        for i, line in enumerate(DECISION_LINES)
    )
    out.append(
        f'<text x="{d_cx}" y="{stack_mid - LINE_H / 2 + DECISION_TEXT_OFFSET_Y}" text-anchor="middle" '
        f'dominant-baseline="middle" fill="{NAVY}" font-size="{FONT}" '
        f'font-family="{FONT_FAMILY}">{spans}</text>'
    )

    out.append(box(stack_x, p2_y, BOX_W, box_h, OVERVIEW_PAIR[0]))
    out.append(box(stack_x, p3_y, BOX_W, box_h, OVERVIEW_PAIR[1]))
    out.append(box(end_box_x, end_box_y, end_w, end_h, OVERVIEW_END))

    # Each leg leaves the vertex it belongs to, turns once, and runs level into
    # its box. Leaving the point rather than the sloped face is the convention
    # readers expect, and it puts the two legs on opposite sides of the shape
    # instead of side by side on the same face.
    for y_leg, tag, up in ((p2_mid, "Yes", True), (p3_mid, "No", False)):
        vertex_y = stack_mid - diamond_h / 2 if up else stack_mid + diamond_h / 2
        out.append(
            f'<path d="M {d_cx} {vertex_y} V {y_leg} H {stack_x - 2}" fill="none" '
            f'stroke="{GRAY_DARK}" stroke-width="{STROKE}" marker-end="url(#b)"/>'
        )
        out.append(label((d_cx + stack_x) / 2, y_leg - PAD_Y, tag))

    out.append(arrow(stack_cx, p2_y + box_h, stack_cx, p3_y - 2, "b"))
    out.append(arrow(stack_x + BOX_W, p3_mid, end_box_x - 2, p3_mid, "b"))
    out.append("</svg>")
    return "".join(out), fig_h, fig_w


# Headers name the stage and print blue bold; the body says what to do. The
# overview follows the same pattern as the procedure figures so the three
# figures read as one set.
OVERVIEW_ROW1 = [
    {"lines": ["Start"], "kind": "terminator"},
    {"header": "Pre-flight", "lines": ["CIMC, ISO,", "DNS/NTP"]},
    {"header": "Procedure 1", "lines": ["Optional: Re-image", "ND-1", "Bootstrap ND-1"]},
]
OVERVIEW_PAIR = [
    {"header": "Procedure 2", "lines": ["Optional: Re-image", "ND-2, ND-3"]},
    {"header": "Procedure 3", "lines": ["Cluster bringup"]},
]
OVERVIEW_END = {"lines": ["Healthy 3-node", "ND cluster"], "kind": "terminator"}
# Procedure 1 always bootstraps ND-1. Its first half re-images ND-1 only when
# start_mode is iso_reimage. Procedure 2 re-images ND-2 and ND-3 in that mode.
# Procedure 3 configures ND-2 and ND-3 during cluster bringup.
DECISION_LINES = ["Re-image from", "ISO?"]

PROC1 = [
    [
        {"header": "CIMC", "lines": ["Mount ND ISO", "via vMedia"]},
        {"header": "vKVM", "lines": ["F6 → UEFI:", "CIMC-Mapped vDVD"]},
        {"header": "SOL", "lines": ["Type 'skip' at", "reuse prompt"]},
        {"header": "SOL", "lines": ["Installer runs;", "node powers off"]},
    ],
    [
        {"header": "CIMC", "lines": ["Unmount vMedia"]},
        {"header": "CIMC", "lines": ["Power on host"]},
        {"header": "SOL", "lines": ["First-boot setup:", "admin pw, IP, GW"]},
        {"header": "Verify", "lines": ["ND-1 mgmt UI up", "HTTP 200"], "kind": "terminal"},
    ],
]

# Three rows, one wizard phase per row: enter and configure cluster-wide
# settings, then per-node details, then commit and verify. Boxes are grouped so
# each one is a step a reader can act on, not a fragment of one.
PROC3 = [
    [
        {"header": "Browser", "lines": ["Log in to ND-1 UI,", "cancel pop-up"]},
        {"header": "Wizard", "lines": ["Cluster Bringup"]},
        {"header": "Basic Information", "lines": ["Cluster name,", "LAN mode"]},
        {"header": "Configuration", "lines": ["DNS, NTP, proxy,", "advanced"]},
    ],
    [
        {"header": "Node Details", "lines": ["Connectivity: L2"]},
        {"header": "Node Details", "lines": ["Edit ND-1 primary:", "mgmt + data nets"]},
        {"header": "Node Details", "lines": ["Add ND-2, ND-3:", "CIMC verify each"]},
        {"header": "Node Details", "lines": ["Validate full", "node set"]},
    ],
    [
        {"header": "Persistent IPs", "lines": ["≥ 5 from the ND", "data subnet"]},
        {"header": "Summary", "lines": ["Review, Save,", "Continue"]},
        {"header": "Install", "lines": ["30–60 min +", "services up"]},
        {"header": "Verify", "lines": ["3 nodes Active;", "acs health"], "kind": "terminal"},
    ],
]

FONT = round(BODY_PT / 72 * UNITS_PER_IN, 2)
HEADER_FONT = round(FONT * HEADER_RATIO, 2)
LINE_H = round(FONT * LINE_RATIO, 2)

check_labels_fit([PROC1, PROC3, [OVERVIEW_ROW1, OVERVIEW_PAIR + [OVERVIEW_END]]])


def find_chrome() -> Path | None:
    """Reuse the Chromium the mermaid build already requires."""
    cache = Path.home() / ".cache/puppeteer"
    if cache.is_dir():
        for candidate in sorted(cache.rglob("chrome-headless-shell")):
            if candidate.is_file():
                return candidate
    for name in ("chromium", "google-chrome"):
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


def rasterize(svg_path: Path, png_path: Path, width: int, height: int, scale: int = 4) -> bool:
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
                f"--force-device-scale-factor={scale}",
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
    print(
        f"scale: {UNITS_PER_IN} units/in, box {BOX_W} units wide, "
        f"body {FONT} units = {FONT / UNITS_PER_IN * 72:.1f}pt, "
        f"header {HEADER_FONT / UNITS_PER_IN * 72:.1f}pt"
    )
    figures = [
        ("nd-deployment-workflow", overview_figure()),
        ("nd-procedure-1-first-node", wrapped_figure(PROC1)),
        ("nd-procedure-3-cluster-bringup", wrapped_figure(PROC3)),
    ]
    for name, (svg, height, width) in figures:
        svg_path = OUT_DIR / f"{name}.svg"
        png_path = OUT_DIR / f"{name}.png"
        svg_path.write_text(svg, encoding="utf-8")
        ok = rasterize(svg_path, png_path, width, height)
        status = "png ok" if ok else "png SKIPPED"
        print(
            f"{name}: {width}x{height} svg ok, {status}, "
            f"embed at width={width / UNITS_PER_IN:.2f}in"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
