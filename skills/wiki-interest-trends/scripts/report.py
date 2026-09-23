#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["reportlab==5.0.1", "matplotlib==3.11.2"]
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
import json
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle

from wikitrends.chart import render_chart
from wikitrends.cli import run_cli
from wikitrends.errors import AppError
from wikitrends.i18n import DEFAULT_LANG, SUPPORTED_LANGS, pick
from wikitrends.trust import Reason, render_reason

FONTS_DIR = Path(__file__).resolve().parent.parent / "assets" / "fonts"
MAX_TABLE_ROWS = 8

LABELS: Dict[str, Dict[str, Any]] = {
    "uk": {
        "title": "Звіт про інтерес до теми у Wikipedia",
        "question": "Питання",
        "conclusion": "Висновок",
        "no_conclusion": "Висновок не надано.",
        "chart": "Динаміка інтересу (нормалізовано, перегляди на мільйон)",
        "table_header": ["Стаття", "Мова", "Перегляди/міс", "YoY", "Тренд", "Довіра"],
        "not_found": "немає даних",
        "more_rows": "... ще {n} у analysis.json",
        "trust": "Рівень довіри",
        "limitations": "Припущення й обмеження",
        "source": "Джерело даних",
        "source_value": "Wikimedia Pageviews API + Wikidata",
        "generated": "Сформовано",
        "trend_values": {"increasing": "зростає", "decreasing": "спадає", "no trend": "без тренду"},
        "trust_values": {"high": "висока", "medium": "середня", "low": "низька", "--": "--"},
    },
    "en": {
        "title": "Wikipedia topic interest report",
        "question": "Question",
        "conclusion": "Conclusion",
        "no_conclusion": "No conclusion provided.",
        "chart": "Interest over time (normalized, views per million)",
        "table_header": ["Article", "Lang", "Views/mo", "YoY", "Trend", "Trust"],
        "not_found": "no data",
        "more_rows": "... {n} more in analysis.json",
        "trust": "Trust level",
        "limitations": "Assumptions & limitations",
        "source": "Data source",
        "source_value": "Wikimedia Pageviews API + Wikidata",
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
    if "DejaVuSans" in pdfmetrics.getRegisteredFontNames():
        return
    pdfmetrics.registerFont(TTFont("DejaVuSans", str(regular)))
    pdfmetrics.registerFont(TTFont("DejaVuSans-Bold", str(bold)))


def _wrap(text: str, width_chars: int) -> List[str]:
    lines: List[str] = []
    for paragraph in text.splitlines() or [""]:
        wrapped = textwrap.wrap(paragraph, width=width_chars) or [""]
        lines.extend(wrapped)
    return lines


def _format_pct(value: Optional[float]) -> str:
    if value is None:
        return "--"
    return f"{value:+.0%}"


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
    crowding, which MAX_TABLE_ROWS and conservative sizing manage."""
    labels = pick(LABELS, lang)
    _register_fonts()
    generated_at = generated_at or datetime.now(timezone.utc)

    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    page_w, page_h = A4
    margin = 15 * mm
    content_w = page_w - 2 * margin
    c = canvas.Canvas(str(output_path), pagesize=A4)
    y = page_h - margin

    def heading(text: str, size: float = 11, font: str = "DejaVuSans-Bold", gap: float = 1.3):
        nonlocal y
        c.setFont(font, size)
        c.drawString(margin, y, text)
        y -= size * gap

    def paragraph(text: str, size: float = 9.5, font: str = "DejaVuSans", max_lines: Optional[int] = None):
        nonlocal y
        c.setFont(font, size)
        chars_per_line = max(20, int(content_w / (size * 0.52)))
        lines = _wrap(text, chars_per_line)
        if max_lines is not None and len(lines) > max_lines:
            lines = lines[: max_lines - 1] + [lines[max_lines - 1].rstrip() + " ..."]
        for line in lines:
            c.drawString(margin, y, line)
            y -= size * 1.25

    heading(title or labels["title"], size=15, gap=1.5)

    if question:
        heading(labels["question"] + ":", size=9.5)
        paragraph(question, max_lines=2)
        y -= 2 * mm

    heading(labels["conclusion"] + ":", size=9.5)
    paragraph(summary or labels["no_conclusion"], max_lines=4)
    y -= 3 * mm

    series = [s for s in analysis.get("series", []) if s.get("found")]
    not_found = [s for s in analysis.get("series", []) if not s.get("found")]

    if series:
        # Redrawn here rather than reusing analyze.py's chart.png: that one
        # is drawn before the report's language is known.
        chart_path = output_path.with_suffix(".chart.png")
        render_chart({s["label"]: s["normalized"] for s in series}, chart_path, lang=lang)
        heading(labels["chart"], size=9.5)
        img_h = 55 * mm
        img_w = content_w
        c.drawImage(
            str(chart_path), margin, y - img_h, width=img_w, height=img_h,
            preserveAspectRatio=True, anchor="n", mask="auto",
        )
        y -= img_h + 4 * mm

        rows = [labels["table_header"]]
        for s in series[:MAX_TABLE_ROWS]:
            m = s["metrics"]
            rows.append(
                [
                    s["article"] or "",
                    s["lang"],
                    f"{m['avg_monthly_views']:.0f}",
                    _format_pct(m["yoy_growth_raw"]),
                    labels["trend_values"].get(m["mann_kendall"]["trend"], m["mann_kendall"]["trend"]),
                    labels["trust_values"].get(s["trust"]["level"], s["trust"]["level"]),
                ]
            )
        table = Table(rows, colWidths=[content_w * w for w in (0.34, 0.08, 0.16, 0.12, 0.16, 0.14)])
        table.setStyle(
            TableStyle(
                [
                    ("FONTNAME", (0, 0), (-1, -1), "DejaVuSans"),
                    ("FONTNAME", (0, 0), (-1, 0), "DejaVuSans-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.3, colors.grey),
                    ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                    ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ("TOPPADDING", (0, 0), (-1, -1), 2),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                ]
            )
        )
        table_w, table_h = table.wrapOn(c, content_w, y - margin)
        table.drawOn(c, margin, y - table_h)
        y -= table_h + 2 * mm
        remaining = len(series) - MAX_TABLE_ROWS + len(not_found)
        if remaining > 0:
            c.setFont("DejaVuSans", 7.5)
            c.drawString(margin, y, labels["more_rows"].format(n=remaining))
            y -= 7.5 * 1.3

    y -= 2 * mm
    trust_levels = [s["trust"]["level"] for s in series]
    worst_trust = "low" if "low" in trust_levels else ("medium" if "medium" in trust_levels else ("high" if trust_levels else "--"))
    heading(f"{labels['trust']}: {labels['trust_values'][worst_trust]}", size=9.5)

    reasons: List[str] = []
    seen = set()
    for s in series:
        # Render each reason in the report's own language from its
        # code+params, not the English "reasons" strings analysis.json also
        # carries -- otherwise a uk-language report ends up with this one
        # section stuck in English. See docs/dev/stats-and-trust.md.
        for rc in s["trust"]["reason_codes"]:
            text = render_reason(Reason(rc["code"], rc["params"]), lang=lang)
            if text not in seen:
                seen.add(text)
                reasons.append(text)
    for w in analysis.get("warnings", []):
        if w not in seen:
            seen.add(w)
            reasons.append(w)

    heading(labels["limitations"] + ":", size=9.5)
    bullet_budget_lines = max(2, int((y - margin - 14 * mm) / (8 * 1.25)))
    lines_used = 0
    c.setFont("DejaVuSans", 8)
    for reason in reasons:
        for line in _wrap("- " + reason, max(20, int(content_w / (8 * 0.52)))):
            if lines_used >= bullet_budget_lines:
                break
            c.drawString(margin, y, line)
            y -= 8 * 1.25
            lines_used += 1
        if lines_used >= bullet_budget_lines:
            c.drawString(margin, y, "...")
            y -= 8 * 1.25
            break

    footer_y = margin
    c.setFont("DejaVuSans", 7.5)
    c.drawString(
        margin, footer_y,
        f"{labels['source']}: {labels['source_value']} | "
        f"{labels['generated']}: {generated_at.strftime('%Y-%m-%d %H:%M UTC')}",
    )

    c.showPage()
    c.save()


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
