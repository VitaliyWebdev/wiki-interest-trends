#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["reportlab==5.0.1", "matplotlib==3.11.2", "pypdf==6.19.0"]
# ///
"""report.py -- turn analyze.py's analysis.json into a one-page PDF report.

The script never invents a conclusion. Trust level, reasons, and warnings
come straight from analysis.json; the actual "here's what this means"
summary is the agent's job, passed in with --summary (or --summary-file).

Examples:
  uv run scripts/report.py --analysis-json wikitrends-out/RUN/analysis.json --lang uk \\
      --question "Чи росте інтерес до інтервального голодування?" \\
      --summary "Інтерес в укр. розділі знижується (-42% р/р), у чеському теж."

  uv run scripts/report.py --analysis-json wikitrends-out/RUN/analysis.json --lang en \\
      --summary-file conclusion.txt --title "Fasting interest report"
"""
import argparse
import io
import json
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, NamedTuple, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from pypdf import PdfReader, PdfWriter, Transformation
from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import simpleSplit
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Flowable, Table, TableStyle

from wikitrends import theme
from wikitrends.chart import FIGURE_PAD_PT, render_chart
from wikitrends.cli import run_cli
from wikitrends.errors import AppError
from wikitrends.i18n import DEFAULT_LANG, SUPPORTED_LANGS, format_compact, format_int, format_pct, month_label, pick
from wikitrends.trust import Reason, render_reason

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
REGULAR, BOLD = "DejaVuSans", "DejaVuSans-Bold"

PAGE_W, PAGE_H = A4
MARGIN = 15 * mm
CONTENT_W = PAGE_W - 2 * MARGIN  # 180 mm, the chart's native width (chart.FIGSIZE)
FOOTER_H = 7 * mm
# Chart lines and table rows stop at the palette's size, so no two series
# shown ever share a color -- the rest are counted in a "... N more" note.
MAX_TABLE_ROWS = len(theme.SERIES_COLORS)
MAX_SERIES_CARDS = 3  # plus the trust card: at most four across
CARD_H = 27 * mm
CARD_PAD = 3.5 * mm

LABELS: Dict[str, Dict[str, Any]] = {
    "uk": {
        "overline": "ТРЕНДИ ІНТЕРЕСУ У WIKIPEDIA",
        "title": "Звіт про інтерес до теми у Wikipedia",
        "question": "Питання",
        "conclusion": "Висновок",
        "no_conclusion": "Висновок не надано.",
        "editions": "Розділи",
        "yoy_caption": "останні 12 міс. проти попередніх 12",
        "yoy_caption_short": "проти попередніх 12 міс.",
        "no_yoy": "замало даних для YoY",
        "views_per_month": "перегл./міс.",
        "trust": "Довіра",
        "trust_worst": "найнижча серед {n} рядів",
        "checks_passed": "{passed} з {total} перевірок пройдено",
        "details": "Деталі по рядах",
        "table_header": ["Стаття", "Мова", "Динаміка", "Перегляди/міс", "YoY", "YoY скор.", "Тренд", "Довіра"],
        "not_found": "статті в цьому розділі немає",
        "more_rows": "... ще {n} у analysis.json",
        "why_trust": "Чому така довіра",
        "all_series": "Усі ряди",
        "more_reasons": "… решта — в analysis.json",
        "how_to_read": "Як читати цей звіт",
        "method": [
            "Нормалізація: перегляди на мільйон усіх переглядів розділу, щоб його власний ріст "
            "чи спад не видавався за зміну інтересу.",
            "YoY: останні 12 міс. проти попередніх 12 (повні роки знімають сезонність). "
            "YoY скор. — те саме на нормалізованих даних.",
            "Тренд: тест Манна–Кендалла; напрям стверджується лише при p < 0,05.",
            "Довіра: довжина історії, обсяг, значущість, збіг після нормалізації, сплески.",
        ],
        "source": "Дані",
        "source_value": "Wikimedia Pageviews API (перегляди людьми, усі платформи) + Wikidata",
        "generated": "Сформовано",
        "trend_values": {"increasing": "зростає", "decreasing": "спадає", "no trend": "без тренду"},
        "trust_values": {"high": "висока", "medium": "середня", "low": "низька", "--": "--"},
    },
    "en": {
        "overline": "WIKIPEDIA INTEREST TRENDS",
        "title": "Wikipedia topic interest report",
        "question": "Question",
        "conclusion": "Conclusion",
        "no_conclusion": "No conclusion provided.",
        "editions": "Editions",
        "yoy_caption": "last 12 months vs the previous 12",
        "yoy_caption_short": "vs the previous 12 months",
        "no_yoy": "not enough data for YoY",
        "views_per_month": "views/mo",
        "trust": "Trust",
        "trust_worst": "lowest of {n} series",
        "checks_passed": "{passed} of {total} checks passed",
        "details": "Details by series",
        "table_header": ["Article", "Lang", "Over time", "Views/mo", "YoY", "YoY adj.", "Trend", "Trust"],
        "not_found": "no article in this edition",
        "more_rows": "... {n} more in analysis.json",
        "why_trust": "Why this trust level",
        "all_series": "All series",
        "more_reasons": "… the rest is in analysis.json",
        "how_to_read": "How to read this",
        "method": [
            "Normalized: views per million of all the edition's views, so its own growth or "
            "decline isn't mistaken for a change in interest.",
            "YoY: the last 12 months vs the 12 before (whole years cancel out seasonality). "
            "YoY adj.: the same, on normalized views.",
            "Trend: Mann-Kendall test; a direction is only claimed at p < 0.05.",
            "Trust: history length, volume, significance, agreement after normalization, spikes.",
        ],
        "source": "Data",
        "source_value": "Wikimedia Pageviews API (human traffic, all platforms) + Wikidata",
        "generated": "Generated",
        "trend_values": {"increasing": "increasing", "decreasing": "decreasing", "no trend": "no trend"},
        "trust_values": {"high": "high", "medium": "medium", "low": "low", "--": "--"},
    },
}


def _register_fonts() -> None:
    regular = FONTS_DIR / "DejaVuSans.ttf"
    bold = FONTS_DIR / "DejaVuSans-Bold.ttf"
    if not regular.exists() or not bold.exists():
        raise AppError(
            error_code="fonts_missing",
            message=f"DejaVu fonts not found under {FONTS_DIR}",
            hint="Re-fetch assets/fonts/DejaVuSans.ttf and DejaVuSans-Bold.ttf.",
        )
    # pdfmetrics' font registry is a process-global singleton -- re-registering
    # the same font name twice in one process is wasted work (though harmless),
    # so skip it once done. The existence check above still runs every call.
    if REGULAR in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont(REGULAR, str(regular)))
    pdfmetrics.registerFont(TTFont(BOLD, str(bold)))


# ---------------------------------------------------------------- text


def _fit(text: str, font: str, size: float, width: float, ellipsis: bool = False) -> str:
    """Shortens text to fit `width`, ending it in "…" if anything was cut
    -- or always, with ellipsis=True, to mark that more text was dropped."""
    if not ellipsis and stringWidth(text, font, size) <= width:
        return text
    while text and stringWidth(text.rstrip() + "…", font, size) > width:
        text = text[:-1]
    return text.rstrip() + "…"


def _first_that_fits(options: List[str], font: str, size: float, width: float) -> str:
    """The first of several phrasings, longest first, that fits whole --
    a shorter wording reads better than a longer one cut off mid-word."""
    for option in options:
        if stringWidth(option, font, size) <= width:
            return option
    return _fit(options[-1], font, size, width)


def _wrap(text: str, font: str, size: float, width: float, max_lines: Optional[int] = None) -> List[str]:
    """Wraps by the font's real glyph widths (not a character count, which
    broke lines early for narrow letters and ran long for wide ones)."""
    lines: List[str] = []
    for paragraph in text.splitlines() or [""]:
        lines.extend(simpleSplit(paragraph, font, size, width) or [""])
    if max_lines is not None and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = _fit(lines[-1], font, size, width, ellipsis=True)
    return lines


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


class _Page:
    """The canvas plus a top-down cursor: each section draws from self.y
    down and leaves self.y below itself."""

    def __init__(self, c: canvas.Canvas):
        self.c = c
        self.y = PAGE_H - MARGIN

    def text(self, x: float, baseline: float, s: str, font: str = REGULAR, size: float = 8,
             color: str = theme.INK, right: bool = False, char_space: float = 0) -> None:
        self.c.setFont(font, size)
        self.c.setFillColor(HexColor(color))
        draw = self.c.drawRightString if right else self.c.drawString
        draw(x, baseline, s, charSpace=char_space)

    def lines(self, lines: List[str], x: float, font: str, size: float, leading: float,
              color: str = theme.INK) -> None:
        """Draws a block whose top edge is self.y; leaves self.y at its bottom edge."""
        baseline = self.y - size * 0.8
        for line in lines:
            self.text(x, baseline, line, font, size, color)
            baseline -= leading
        self.y -= size * 0.8 + leading * (len(lines) - 1) + size * 0.25

    def box(self, x: float, top: float, w: float, h: float, color: str) -> None:
        self.c.setFillColor(HexColor(color))
        self.c.roundRect(x, top - h, w, h, 2 * mm, stroke=0, fill=1)


# ---------------------------------------------------------------- data


def _direction_style(change: Optional[float], trend: str) -> Tuple[str, str]:
    """(color, arrow) for a YoY number. Colored only when the Mann-Kendall
    trend is significant *and* agrees with the number's sign -- a -3% the
    test calls "no trend" stays grey instead of reading as a decline."""
    if change is not None and trend == "increasing" and change > 0:
        return theme.UP, "▲"
    if change is not None and trend == "decreasing" and change < 0:
        return theme.DOWN, "▼"
    return theme.FLAT, ""


def _worst_trust(series: List[Dict[str, Any]]) -> str:
    levels = [s["trust"]["level"] for s in series]
    for level in ("low", "medium", "high"):
        if level in levels:
            return level
    return "--"


def _period(series: List[Dict[str, Any]], lang: str) -> Optional[str]:
    """The data's own date range: "Sep 2024 – Aug 2026" for monthly data,
    "25 Aug 2026 – 23 Sep 2026" once any point isn't on the 1st (daily)."""
    stamps = sorted(p["timestamp"] for s in series for p in s["normalized"])
    if not stamps:
        return None
    daily = any(t[6:8] != "01" for t in stamps)

    def label(t: str) -> str:
        month = month_label(int(t[4:6]), int(t[:4]), lang)
        return f"{int(t[6:8])} {month}" if daily else month

    return f"{label(stamps[0])} – {label(stamps[-1])}"


def _reasons(s: Dict[str, Any], lang: str) -> List[Tuple[Optional[bool], str]]:
    """(is_concern, text) per trust reason, rendered in the report's own
    language from code+params -- not the English "reasons" strings
    analysis.json also carries (see docs/dev/stats-and-trust.md).
    is_concern is None for an analysis.json written before the flag existed."""
    out = []
    for rc in s["trust"]["reason_codes"]:
        text = render_reason(Reason(rc["code"], rc["params"]), lang=lang)
        out.append((rc.get("concern"), text))
    return out


# ---------------------------------------------------------------- sections


def _draw_header(page: _Page, labels: Dict[str, Any], heading: str, question: Optional[str], meta: List[str]) -> None:
    page.text(MARGIN, page.y - 7, labels["overline"], BOLD, 7.5, theme.ACCENT, char_space=0.8)
    page.y -= 7 + 4 * mm
    # The heading is often the user's own question, which can be long:
    # step down to a smaller size before cutting any of it off.
    for size, max_lines in ((18, 2), (14, 3)):
        lines = _wrap(heading, BOLD, size, CONTENT_W)
        if len(lines) <= max_lines:
            break
    page.lines(_wrap(heading, BOLD, size, CONTENT_W, max_lines=max_lines), MARGIN, BOLD, size, size * 1.22)
    if question:
        page.y -= 2 * mm
        text = f"{labels['question']}: {question}"
        page.lines(_wrap(text, REGULAR, 9.5, CONTENT_W, max_lines=2), MARGIN, REGULAR, 9.5, 12.5, theme.MUTED)
    if meta:
        page.y -= 2.5 * mm
        page.lines([_fit(" · ".join(meta), REGULAR, 8, CONTENT_W)], MARGIN, REGULAR, 8, 10, theme.MUTED)
    page.y -= 4 * mm
    page.c.setStrokeColor(HexColor(theme.RULE))
    page.c.setLineWidth(0.6)
    page.c.line(MARGIN, page.y, MARGIN + CONTENT_W, page.y)
    page.y -= 5 * mm


def _draw_conclusion(page: _Page, labels: Dict[str, Any], summary: Optional[str]) -> None:
    pad = 4 * mm
    lines = _wrap(summary or labels["no_conclusion"], REGULAR, 10, CONTENT_W - 2 * pad, max_lines=6)
    body_h = 10 * 0.8 + 14 * (len(lines) - 1) + 10 * 0.25
    h = pad + 8 + 2 * mm + body_h + pad
    top = page.y
    page.box(MARGIN, top, CONTENT_W, h, theme.ACCENT_TINT)
    page.text(MARGIN + pad, top - pad - 6.5, labels["conclusion"], BOLD, 8, theme.ACCENT)
    page.y = top - pad - 8 - 2 * mm
    page.lines(lines, MARGIN + pad, REGULAR, 10, 14)
    page.y = top - h - 5 * mm


def _card(page: _Page, x: float, top: float, w: float, label: str, label_x_offset: float = 0) -> Tuple[float, float]:
    """Draws a card's background and top label; returns the baselines for
    its big value and the caption under it, shared by every card type so
    a row of cards lines up."""
    page.box(x, top, w, CARD_H, theme.SURFACE)
    label = _fit(label, REGULAR, 7.5, w - 2 * CARD_PAD - label_x_offset)
    page.text(x + CARD_PAD + label_x_offset, top - CARD_PAD - 5.3, label, REGULAR, 7.5, theme.MUTED)
    value_baseline = top - CARD_PAD - 8 - 3 * mm - 20 * 0.72
    return value_baseline, value_baseline - 11


def _draw_series_card(page: _Page, labels: Dict[str, Any], s: Dict[str, Any], color: str,
                      x: float, top: float, w: float, lang: str) -> None:
    pad = CARD_PAD
    m = s["metrics"]
    trend = m["mann_kendall"]["trend"]
    yoy = m["yoy_growth_raw"]
    baseline, caption_baseline = _card(page, x, top, w, f"{s['article']} · {s['lang']}", 3.5 * mm)
    page.c.setFillColor(HexColor(color))
    page.c.circle(x + pad + 1.2 * mm, top - pad - 2.6, 1.2 * mm, stroke=0, fill=1)

    value_color, arrow = _direction_style(yoy, trend)
    value_x = x + pad
    if arrow:
        page.text(value_x, baseline + 2, arrow, BOLD, 11, value_color)
        value_x += stringWidth(arrow, BOLD, 11) + 1.2 * mm
    page.text(value_x, baseline, format_pct(yoy), BOLD, 20, value_color)
    captions = [labels["yoy_caption"], labels["yoy_caption_short"]] if yoy is not None else [labels["no_yoy"]]
    page.text(x + pad, caption_baseline, _first_that_fits(captions, REGULAR, 7, w - 2 * pad), REGULAR, 7, theme.FAINT)

    views = f"{format_compact(m['avg_monthly_views'], lang)} {labels['views_per_month']}"
    footer = [f"{views} · {labels['trend_values'].get(trend, trend)}", views]  # the table has the trend too
    page.text(x + pad, top - CARD_H + pad, _first_that_fits(footer, REGULAR, 7.5, w - 2 * pad), REGULAR, 7.5, theme.MUTED)


def _draw_trust_card(page: _Page, labels: Dict[str, Any], series: List[Dict[str, Any]],
                     x: float, top: float, w: float) -> None:
    level = _worst_trust(series)
    baseline, caption_baseline = _card(page, x, top, w, labels["trust"])
    color = theme.TRUST_COLORS.get(level, theme.FLAT)
    page.text(x + CARD_PAD, baseline, _capitalize(labels["trust_values"][level]), BOLD, 20, color)

    if len(series) > 1:
        caption = labels["trust_worst"].format(n=len(series))
    else:
        flags = [concern for concern, _ in _reasons(series[0], DEFAULT_LANG)]
        caption = "" if None in flags else labels["checks_passed"].format(
            passed=flags.count(False), total=len(flags)
        )
    page.text(x + CARD_PAD, caption_baseline, _fit(caption, REGULAR, 7, w - 2 * CARD_PAD), REGULAR, 7, theme.FAINT)


def _draw_cards(page: _Page, labels: Dict[str, Any], series: List[Dict[str, Any]], lang: str) -> None:
    """Headline numbers first, per dashboard convention: one card per
    series (up to MAX_SERIES_CARDS -- the table below has every row) plus
    an overall trust card. Each card's dot is its chart line's color."""
    shown = series[:MAX_SERIES_CARDS]
    gap = 4 * mm
    n = len(shown) + 1
    w = (CONTENT_W - gap * (n - 1)) / n
    for i, s in enumerate(shown):
        _draw_series_card(page, labels, s, theme.series_color(i), MARGIN + i * (w + gap), page.y, w, lang)
    _draw_trust_card(page, labels, series, MARGIN + len(shown) * (w + gap), page.y, w)
    page.y -= CARD_H + 6 * mm


class _Sparkline(Flowable):
    """A word-sized line (Tufte): the row's own shape on its own scale,
    in its chart line's color -- which also makes it the row's color key."""

    def __init__(self, values: List[float], color: str, width: float, height: float):
        super().__init__()
        self.values, self.color, self.width, self.height = values, color, width, height

    def wrap(self, *_):
        return self.width, self.height

    def draw(self):
        lo, hi = min(self.values), max(self.values)
        span = (hi - lo) or 1.0
        step = self.width / max(1, len(self.values) - 1)
        points = [(i * step, (v - lo) / span * self.height) for i, v in enumerate(self.values)]
        self.canv.setStrokeColor(HexColor(self.color))
        self.canv.setFillColor(HexColor(self.color))
        self.canv.setLineWidth(0.9)
        self.canv.setLineJoin(1)
        path = self.canv.beginPath()
        path.moveTo(*points[0])
        for point in points[1:]:
            path.lineTo(*point)
        self.canv.drawPath(path, stroke=1, fill=0)
        self.canv.circle(*points[-1], 1.1, stroke=0, fill=1)


def _draw_table(page: _Page, labels: Dict[str, Any], found: List[Dict[str, Any]],
                not_found: List[Dict[str, Any]], lang: str) -> None:
    page.lines([labels["details"]], MARGIN, BOLD, 10, 12)
    page.y -= 2 * mm

    fractions = (0.25, 0.06, 0.15, 0.13, 0.09, 0.10, 0.13, 0.09)
    widths = [CONTENT_W * f for f in fractions]
    cell_pad = 3
    rows: List[List[Any]] = [labels["table_header"]]
    style = [
        ("FONTNAME", (0, 0), (-1, -1), REGULAR),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("TEXTCOLOR", (0, 0), (-1, -1), HexColor(theme.INK)),
        ("FONTNAME", (0, 0), (-1, 0), BOLD),
        ("FONTSIZE", (0, 0), (-1, 0), 7),
        ("TEXTCOLOR", (0, 0), (-1, 0), HexColor(theme.MUTED)),
        ("LINEBELOW", (0, 0), (-1, 0), 0.7, HexColor(theme.FAINT)),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, HexColor(theme.RULE)),
        ("ALIGN", (3, 0), (5, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5),
        ("LEFTPADDING", (0, 0), (-1, -1), cell_pad),
        ("RIGHTPADDING", (0, 0), (-1, -1), cell_pad),
        ("LEFTPADDING", (0, 0), (0, -1), 0),  # flush with the page's left text edge
        ("LEFTPADDING", (6, 0), (6, -1), 10),  # gap after the right-aligned numbers
    ]

    for i, s in enumerate(found[:MAX_TABLE_ROWS]):
        m = s["metrics"]
        trend = m["mann_kendall"]["trend"]
        level = s["trust"]["level"]
        values = [p["per_million"] for p in s["normalized"]]
        r = len(rows)
        rows.append([
            _fit(s["article"] or "", REGULAR, 8, widths[0] - cell_pad),
            s["lang"],
            _Sparkline(values, theme.series_color(i), widths[2] - 2 * cell_pad, 12) if values else "",
            format_int(m["avg_monthly_views"], lang),
            format_pct(m["yoy_growth_raw"]),
            format_pct(m.get("yoy_growth_normalized")),
            labels["trend_values"].get(trend, trend),
            labels["trust_values"].get(level, level),
        ])
        style += [
            ("TEXTCOLOR", (4, r), (4, r), HexColor(_direction_style(m["yoy_growth_raw"], trend)[0])),
            ("FONTNAME", (4, r), (4, r), BOLD),
            ("TEXTCOLOR", (5, r), (5, r), HexColor(theme.MUTED)),
            ("TEXTCOLOR", (7, r), (7, r), HexColor(theme.TRUST_COLORS.get(level, theme.FLAT))),
        ]
    for s in not_found[: max(0, MAX_TABLE_ROWS - len(found))]:
        r = len(rows)
        rows.append([_fit(s.get("article") or s["label"], REGULAR, 8, widths[0] - cell_pad), s["lang"],
                     labels["not_found"], "", "", "", "", ""])
        style += [("SPAN", (2, r), (-1, r)), ("TEXTCOLOR", (0, r), (-1, r), HexColor(theme.FAINT))]

    table = Table(rows, colWidths=widths)
    table.setStyle(TableStyle(style))
    _, table_h = table.wrapOn(page.c, CONTENT_W, page.y - MARGIN)
    table.drawOn(page.c, MARGIN, page.y - table_h)
    page.y -= table_h

    remaining = len(found) + len(not_found) - (len(rows) - 1)
    if remaining > 0:
        page.y -= 2 * mm
        page.lines([labels["more_rows"].format(n=remaining)], MARGIN, REGULAR, 7.5, 9, theme.MUTED)
    page.y -= 6 * mm


class _ListRow(NamedTuple):
    space_above: float
    marker: Optional[str]  # drawn in the hanging indent, on an entry's first line
    marker_color: str
    indent: float
    text: str
    font: str
    color: str
    starts_entry: bool
    is_group: bool


def _list_rows(entries: List[Tuple[str, str, str]], width: float, size: float) -> List[_ListRow]:
    """entries: (kind, text, color); kind is "group" for a subheading, or
    the marker glyph for a list item, which gets a hanging indent."""
    indent = 3.5 * mm
    rows = []
    for kind, text, color in entries:
        is_group = kind == "group"
        font = BOLD if is_group else REGULAR
        offset = 0 if is_group else indent
        for k, line in enumerate(_wrap(text, font, size, width - offset)):
            rows.append(_ListRow(
                3 if is_group and k == 0 else 0, kind if not is_group and k == 0 else None, color,
                offset, line, font, color if is_group else theme.INK, k == 0, is_group,
            ))
    return rows


def _rows_height(rows: List[_ListRow], leading: float) -> float:
    return sum(leading + (r.space_above if k else 0) for k, r in enumerate(rows))


def _balanced_split(rows: List[_ListRow], capacity: float, leading: float) -> int:
    """Where the second column starts: the first entry boundary past half
    the total height (so the columns come out even, and no entry is split
    across them), moved back if the first column would overflow. Never
    right after a group heading, which would strand it at the bottom of
    column one, away from its items."""
    boundaries = [i for i, r in enumerate(rows) if r.starts_entry and i and not rows[i - 1].is_group] + [len(rows)]
    total = _rows_height(rows, leading)
    split = next(b for b in boundaries if _rows_height(rows[:b], leading) >= total / 2)
    while split and _rows_height(rows[:split], leading) > capacity:
        split = max([b for b in boundaries if b < split] or [0])
    return split


def _draw_columns(page: _Page, entries: List[Tuple[str, str, str]], capacity: float, size: float,
                  leading: float, overflow_note: str) -> None:
    """Two balanced columns of list entries from page.y down, at most
    `capacity` tall; leaves page.y under the taller column. If it doesn't
    all fit, the last line that would fit becomes `overflow_note` -- a
    report that silently dropped reasons would look more certain than it
    is."""
    gap = 8 * mm
    col_w = (CONTENT_W - gap) / 2
    rows = _list_rows(entries, col_w, size)
    if capacity < size:
        return
    split = _balanced_split(rows, capacity, leading)
    top, lowest = page.y, page.y
    for x, column in ((MARGIN, rows[:split]), (MARGIN + col_w + gap, rows[split:])):
        placed = []
        baseline = top - size * 0.8
        for k, row in enumerate(column):
            baseline -= row.space_above if k else 0
            if top - baseline + size * 0.25 > capacity:
                break
            placed.append((baseline, row))
            baseline -= leading
        if len(placed) < len(column):
            last = placed.pop()[0] if placed else top - size * 0.8
            placed.append((last, _ListRow(0, None, theme.MUTED, 0, overflow_note, REGULAR, theme.MUTED, True, False)))
        for baseline, row in placed:
            if row.marker:
                page.text(x, baseline, row.marker, BOLD, size, row.marker_color)
            page.text(x + row.indent, baseline, row.text, row.font, size, row.color)
        if placed:
            lowest = min(lowest, placed[-1][0] - size * 0.25)
    page.y = lowest


def _reason_entries(labels: Dict[str, Any], found: List[Dict[str, Any]], lang: str) -> List[Tuple[str, str, str]]:
    """Concerns first -- they're what a reader must not miss. With several
    series, a reason every series shares (same text, e.g. "24 months of
    data") is listed once under "all series" instead of once per series."""
    markers = {True: ("!", theme.TRUST_COLORS["medium"]), False: ("✓", theme.UP), None: ("•", theme.MUTED)}

    def items(reasons):
        return [(markers[concern][0], text, markers[concern][1]) for concern, text in reasons]

    per_series = []
    for s in found:
        reasons = list(dict.fromkeys(_reasons(s, lang)))  # de-duplicated, order kept
        per_series.append(sorted(reasons, key=lambda r: r[0] is not True))
    if len(found) <= 1:
        return items(per_series[0]) if found else []

    common = [r for r in per_series[0] if all(r in other for other in per_series[1:])]
    entries = [("group", labels["all_series"], theme.INK)] + items(common) if common else []
    for i, (s, reasons) in enumerate(zip(found, per_series)):
        own = [r for r in reasons if r not in common]
        if own:
            entries += [("group", f"{s['article']} · {s['lang']}", theme.series_color(i))] + items(own)
    return entries


def _draw_notes(page: _Page, labels: Dict[str, Any], found: List[Dict[str, Any]],
                warnings: List[str], lang: str) -> None:
    """Why the trust level is what it is, then how to read the numbers --
    in that priority order for the space that's left. The reasons are
    this analysis's own evidence and get all the room they need (cut with
    an overflow note if even that isn't enough); the method notes are the
    same fixed text on every report, so they're only drawn if they fit
    whole."""
    bottom, heading_h, gap = MARGIN + FOOTER_H, 12 + 2 * mm, 5 * mm
    reasons = _reason_entries(labels, found, lang) + [("!", w, theme.TRUST_COLORS["medium"]) for w in warnings]
    # A heading with nothing under it is worse than no section: skip it
    # unless at least a couple of lines fit (the trust card still shows the level).
    if reasons and page.y - bottom >= heading_h + 2 * 9.6:
        page.lines([labels["why_trust"]], MARGIN, BOLD, 10, 12)
        page.y -= 2 * mm
        _draw_columns(page, reasons, page.y - bottom, 7.5, 9.6, labels["more_reasons"])
        page.y -= gap

    method = [("•", t, theme.MUTED) for t in labels["method"]]
    method_rows = _list_rows(method, (CONTENT_W - 8 * mm) / 2, 7)
    split = _balanced_split(method_rows, float("inf"), 9)
    method_h = max(_rows_height(method_rows[:split], 9), _rows_height(method_rows[split:], 9))
    if page.y - bottom >= heading_h + method_h:
        page.lines([labels["how_to_read"]], MARGIN, BOLD, 10, 12)
        page.y -= 2 * mm
        _draw_columns(page, method, page.y - bottom, 7, 9, labels["more_reasons"])


def _draw_footer(page: _Page, labels: Dict[str, Any], generated_at: datetime) -> None:
    y = MARGIN
    page.c.setStrokeColor(HexColor(theme.RULE))
    page.c.setLineWidth(0.6)
    page.c.line(MARGIN, y + 4 * mm, MARGIN + CONTENT_W, y + 4 * mm)
    generated = f"{labels['generated']}: {generated_at.strftime('%Y-%m-%d %H:%M UTC')}"
    source_w = CONTENT_W - stringWidth(generated, REGULAR, 7) - 6 * mm
    page.text(MARGIN, y, _fit(f"{labels['source']}: {labels['source_value']}", REGULAR, 7, source_w), REGULAR, 7, theme.FAINT)
    page.text(MARGIN + CONTENT_W, y, generated, REGULAR, 7, theme.FAINT, right=True)


def _reserve_chart(page: _Page, chart_pdf: Path) -> Tuple[float, float, float]:
    """Leaves room for the chart and returns where to stamp it: (x, y,
    scale). Scaled so the chart's own padding falls outside the page's
    text edges and its title lines up with everything else."""
    box = PdfReader(str(chart_pdf)).pages[0].mediabox
    width, height = float(box.width), float(box.height)
    scale = CONTENT_W / (width - 2 * FIGURE_PAD_PT)
    x = MARGIN - FIGURE_PAD_PT * scale
    y = page.y + FIGURE_PAD_PT * scale - height * scale
    page.y = y - 4 * mm
    return x, y, scale


def _write_pdf(page_pdf: io.BytesIO, chart: Optional[Tuple[Path, Tuple[float, float, float]]],
               output_path: Path, title: str) -> None:
    """Stamps the chart onto the page as vector graphics. reportlab can only
    place raster images, which is why the chart used to be a blurry 150 dpi
    PNG; pypdf merges matplotlib's own PDF output instead, so the chart
    stays sharp at any zoom and its text stays real text."""
    writer = PdfWriter(clone_from=page_pdf)
    page = writer.pages[0]
    if chart:
        chart_pdf, (x, y, scale) = chart
        page.merge_transformed_page(PdfReader(str(chart_pdf)).pages[0], Transformation().scale(scale).translate(x, y))
    page.compress_content_streams()
    writer.add_metadata({"/Title": title, "/Creator": "wiki-interest-trends"})
    with open(output_path, "wb") as f:
        writer.write(f)


def generate_report(
    analysis: Dict[str, Any],
    *,
    output_path: Path,
    lang: str = DEFAULT_LANG,
    title: Optional[str] = None,
    question: Optional[str] = None,
    summary: Optional[str] = None,
    generated_at: Optional[datetime] = None,
) -> None:
    """Renders exactly one PDF page. Uses the raw canvas API (not a
    Platypus doc template) specifically so there is no automatic
    pagination to fight -- a single Canvas with one showPage()/save() call
    structurally cannot produce a second page; the only risk is visual
    crowding, which MAX_TABLE_ROWS, max_lines, and _draw_columns' capacity
    limit manage.

    Top to bottom, most important first: header, the agent's conclusion,
    headline cards, the chart, a per-series table, then why the trust
    level is what it is and how to read the numbers. See
    docs/dev/report-design.md for why each piece is there."""
    labels = pick(LABELS, lang)
    _register_fonts()
    generated_at = generated_at or datetime.now(timezone.utc)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    all_series = analysis.get("series", [])
    found = [s for s in all_series if s.get("found")]
    not_found = [s for s in all_series if not s.get("found")]
    heading = title or question or labels["title"]
    # The generation time is in the footer; the header says what the data covers.
    meta = [m for m in (
        _period(found, lang),
        f"{labels['editions']}: {', '.join(dict.fromkeys(s['lang'] for s in all_series))}" if all_series else None,
    ) if m]

    with tempfile.TemporaryDirectory() as tmp:
        chart = None
        if found:
            # Redrawn here rather than reusing analyze.py's chart.png: that
            # one is drawn before the report's language is known.
            chart_pdf = Path(tmp) / "chart.pdf"
            render_chart({s["label"]: s["normalized"] for s in found[:MAX_TABLE_ROWS]}, chart_pdf, lang=lang)

        buffer = io.BytesIO()
        page = _Page(canvas.Canvas(buffer, pagesize=A4))
        _draw_header(page, labels, heading, question if title else None, meta)
        _draw_conclusion(page, labels, summary)
        if found:
            _draw_cards(page, labels, found, lang)
            chart = (chart_pdf, _reserve_chart(page, chart_pdf))
        if all_series:
            _draw_table(page, labels, found, not_found, lang)
        _draw_notes(page, labels, found, analysis.get("warnings", []), lang)
        _draw_footer(page, labels, generated_at)
        page.c.showPage()
        page.c.save()

        buffer.seek(0)
        _write_pdf(buffer, chart, output_path, heading)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="report.py",
        description="Turn analyze.py's analysis.json into a one-page PDF report.",
        epilog=(
            "Examples:\n"
            "  uv run scripts/report.py --analysis-json wikitrends-out/RUN/analysis.json"
            ' --lang uk --summary "Інтерес знижується (-42% р/р)."\n'
            "  uv run scripts/report.py --analysis-json wikitrends-out/RUN/analysis.json"
            " --lang en --summary-file conclusion.txt --title \"Fasting interest report\"\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--analysis-json", required=True, help="Path to analyze.py's analysis.json")
    parser.add_argument(
        "--lang", default=DEFAULT_LANG,
        help=(
            f"Report language: {' or '.join(SUPPORTED_LANGS)} -- pass the language the user "
            f"is writing in; any other code falls back to {DEFAULT_LANG} (default: {DEFAULT_LANG})"
        ),
    )
    parser.add_argument("--title", help="Custom report title")
    parser.add_argument("--question", help="The user's original question, shown at the top")
    parser.add_argument("--summary", help="The agent's conclusion, based on the numbers in analysis.json")
    parser.add_argument("--summary-file", help="Path to a file containing the conclusion, instead of --summary")
    parser.add_argument("--output", help="Output PDF path (default: report.pdf next to analysis.json)")
    return parser


def main(argv=None) -> None:
    args = build_arg_parser().parse_args(argv)

    def run():
        analysis_path = Path(args.analysis_json)
        if not analysis_path.exists():
            raise AppError(
                error_code="analysis_not_found",
                message=f"No such file: {analysis_path}",
                hint="Run analyze.py first and pass its analysis_json path here.",
            )
        analysis = json.loads(analysis_path.read_text())

        summary = args.summary
        if args.summary_file:
            summary = Path(args.summary_file).read_text().strip()

        output_path = Path(args.output) if args.output else analysis_path.parent / "report.pdf"
        generate_report(
            analysis, output_path=output_path, lang=args.lang, title=args.title,
            question=args.question, summary=summary,
        )
        return {"ok": True, "report_pdf": str(output_path)}

    run_cli(run)


if __name__ == "__main__":
    main()
