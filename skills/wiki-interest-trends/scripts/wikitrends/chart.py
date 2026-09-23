from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Sequence, Tuple

import matplotlib

matplotlib.use("Agg")  # headless: this always runs from a CLI script, never a GUI
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.patheffects import withStroke
from matplotlib.ticker import FuncFormatter, MaxNLocator

from .i18n import DEFAULT_LANG, DECIMAL_SEP, month_label, pick
from .theme import FAINT, INK, MUTED, RULE, SURFACE, series_color

CHART_LABELS: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Interest over time",
        "subtitle_per_million": "Views per million pageviews of the whole language edition",
        "subtitle_index": "Index, 100 = each series' own average · adjusted for the edition's overall traffic",
        "last_12": "last 12 months",
        "peak": "peak",
        "no_data": "No data to plot",
    },
    "uk": {
        "title": "Інтерес у часі",
        "subtitle_per_million": "Перегляди на мільйон усіх переглядів мовного розділу",
        "subtitle_index": "Індекс, 100 = власне середнє кожного ряду · з поправкою на загальний трафік розділу",
        "last_12": "останні 12 міс.",
        "peak": "пік",
        "no_data": "Немає даних для графіка",
    },
}

# 180 x 66 mm -- the PDF report's content width, so report.py embeds the
# chart at (almost exactly) 1:1 and its 8 pt text is really 8 pt, same as
# the table's. Wide rather than tall: a month-to-month line reads best
# when its slopes aren't exaggerated.
FIGSIZE = (7.09, 2.6)
PNG_DPI = 200
MAX_LABEL_CHARS = 30
END_LABEL_GAP_PT = 10  # room for a leader line when a label had to move
FONT_SIZE = 8
# Blank border around everything drawn. report.py shifts the embedded
# chart left by this much so the chart title lines up with the page text.
FIGURE_PAD_PT = 4

_STYLE = {
    # The same font the PDF uses, so chart and page read as one document.
    "font.family": "DejaVu Sans",
    "font.size": FONT_SIZE,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.spines.left": False,
    "axes.edgecolor": RULE,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "grid.color": RULE,
    "grid.linewidth": 0.6,
    "xtick.color": RULE,
    "xtick.labelcolor": MUTED,
    "ytick.labelcolor": MUTED,
    "ytick.left": False,
    # Embed TrueType instead of converting text to outlines: the chart's
    # text stays real text inside report.pdf, so it is selectable,
    # searchable, and checkable by extracting the PDF's text in tests.
    "pdf.fonttype": 42,
}


def _timestamp_to_date(timestamp: str) -> date:
    return date(int(timestamp[0:4]), int(timestamp[4:6]), int(timestamp[6:8]))


def _as_index(values: List[float]) -> List[float]:
    """Rebased so 100 = the series' own average. Two language editions can
    differ 10x in views per million; on a shared axis the smaller one
    flattens into the baseline and its trend becomes invisible."""
    mean = sum(values) / len(values)
    return [v / mean * 100 if mean else 0.0 for v in values]


def _spread(targets: Sequence[float], min_gap: float, top: float) -> List[float]:
    """Moves label positions apart by at least min_gap while keeping each as
    close to its own line end as possible: push overlapping labels up in
    order, then, if that pushed the top one past `top`, push back down."""
    order = sorted(range(len(targets)), key=lambda i: targets[i])
    pos = [targets[i] for i in order]
    for k in range(1, len(pos)):
        pos[k] = max(pos[k], pos[k - 1] + min_gap)
    if pos and pos[-1] > top:
        pos[-1] = top
        for k in range(len(pos) - 2, -1, -1):
            pos[k] = min(pos[k], pos[k + 1] - min_gap)
    result = [0.0] * len(pos)
    for k, i in enumerate(order):
        result[i] = pos[k]
    return result


def _date_axis(ax, first: date, last: date, lang: str) -> date:
    """Returns the right edge of the plotted range."""
    span_days = (last - first).days
    if span_days <= 62:
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=7))
        fmt = lambda d, pos: f"{d.day} {month_label(d.month, None, lang)}"  # noqa: E731
    else:
        months = (1,) if span_days > 6 * 365 else (1, 7) if span_days > 3 * 365 else (1, 4, 7, 10)
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=months))
        # The year goes on the first tick and on every January, not on
        # every tick -- and never on a rotated label.
        fmt = lambda d, pos: month_label(d.month, None, lang) + (f"\n{d.year}" if pos == 0 or d.month == 1 else "")  # noqa: E731
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, pos: fmt(mdates.num2date(x).date(), pos)))
    pad = timedelta(days=max(1, span_days // 60))
    ax.set_xlim(first - pad, last + pad)
    return last + pad


def _value_axis(ax, lang: str) -> None:
    sep = pick(DECIMAL_SEP, lang)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=4, min_n_ticks=3))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, pos: f"{v:g}".replace(".", sep)))


def _annotate(ax, text: str, **kwargs):
    """ax.annotate with a white halo behind the text, so a label a line
    runs through stays readable. The halo is a separate white copy drawn
    underneath: a path effect on the text itself would turn it into
    outlines in PDF output -- no longer text anyone can select, search, or
    check in a test."""
    zorder = kwargs.pop("zorder", 6)
    halo = ax.annotate(text, **{**kwargs, "color": "white", "zorder": zorder - 0.1,
                                "path_effects": [withStroke(linewidth=2.5, foreground="white")]})
    return halo, ax.annotate(text, zorder=zorder, **kwargs)


def _is_monthly(dates: List[date]) -> bool:
    return all((b - a).days >= 28 for a, b in zip(dates, dates[1:]))


def _shade_last_12_months(ax, dates: List[date], end: date, labels: Dict[str, str]) -> None:
    """Shades exactly the window YoY growth compares against the 12 months
    before it (see stats.year_over_year_growth), so the headline number
    has a visible meaning on the chart. Monthly data with a full year
    before that window only -- anything else has no YoY to explain. The
    caption sits just above the plot area, where no line or peak label
    can run into it."""
    if len(dates) < 24 or not _is_monthly(dates):
        return
    start = dates[-12] - (dates[-12] - dates[-13]) / 2
    ax.axvspan(start, end, color=SURFACE, zorder=0, linewidth=0)
    ax.annotate(
        labels["last_12"], xy=(start, 1), xycoords=("data", "axes fraction"), annotation_clip=False,
        xytext=(0, 3), textcoords="offset points", va="bottom", ha="left", fontsize=7, color=FAINT,
    )


def _mark_peaks(ax, plotted, labels: Dict[str, str], lang: str) -> List[Tuple[float, Any, Any]]:
    """Marks each series' highest point and labels it with its date.
    Returns (peak value, halo, text) per label, for _drop_colliding()."""
    all_dates = sorted({d for _, _, xs, _ in plotted for d in xs})
    monthly = _is_monthly(all_dates)
    span = max(1, (all_dates[-1] - all_dates[0]).days)
    marked = []
    for color, _, xs, ys in plotted:
        peak = max(range(len(ys)), key=ys.__getitem__)
        d = xs[peak]
        ax.plot([d], [ys[peak]], "o", markersize=4.5, markerfacecolor="white",
                markeredgecolor=color, markeredgewidth=1.2, zorder=5)
        when = month_label(d.month, d.year, lang) if monthly else f"{d.day} {month_label(d.month, None, lang)}"
        where = (d - all_dates[0]).days / span
        halo, text = _annotate(
            ax, f"{labels['peak']} · {when}",
            xy=(d, ys[peak]), xytext=(0, 6), textcoords="offset points", va="bottom",
            ha="left" if where < 0.15 else "right" if where > 0.85 else "center",
            fontsize=7, color=color,
        )
        marked.append((ys[peak], halo, text))
    return marked


def _drop_colliding(fig, marked: List[Tuple[float, Any, Any]]) -> None:
    """Keeps a peak label only if it doesn't overlap one already kept,
    highest peak first; the marker itself always stays. Two peaks in the
    same month would otherwise print on top of each other."""
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    kept = []
    for _, halo, text in sorted(marked, key=lambda m: -m[0]):
        box = text.get_window_extent(renderer)
        if any(box.overlaps(other) for other in kept):
            halo.remove()
            text.remove()
        else:
            kept.append(box)


def render_chart(
    series_by_label: Dict[str, List[Dict[str, Any]]], output_path: Path, lang: str = DEFAULT_LANG
) -> None:
    """One chart of normalized interest over time, one line per label (a
    "topic (language)" combination). Points are analysis.json's
    series[].normalized entries, so analyze.py and report.py draw from the
    exact same data; the file format follows output_path's suffix (PNG for
    chat, PDF for embedding in report.py as vector graphics).

    Line colors follow the dict's order (theme.series_color(i)), and
    report.py relies on that to color each series' card and table row to
    match -- so a label with no points still takes its color slot, it
    just draws nothing (analyze.py reports those separately).

    One series is drawn in its real unit, views per million; several are
    rebased to an index (see _as_index). Lines are labeled at their ends
    instead of with a legend, which used to cover the data."""
    labels = pick(CHART_LABELS, lang)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    plotted: List[Tuple[str, str, List[date], List[float]]] = []
    for i, (label, points) in enumerate(series_by_label.items()):
        if points:
            values = [p["per_million"] for p in points]
            plotted.append((series_color(i), label, [_timestamp_to_date(p["timestamp"]) for p in points], values))
    as_index = len(plotted) > 1
    if as_index:
        plotted = [(color, label, xs, _as_index(ys)) for color, label, xs, ys in plotted]

    with plt.rc_context(_STYLE):
        fig, ax = plt.subplots(figsize=FIGSIZE)
        pad_x, pad_y = FIGURE_PAD_PT / (FIGSIZE[0] * 72), FIGURE_PAD_PT / (FIGSIZE[1] * 72)
        fig.text(pad_x, 1 - pad_y, labels["title"], ha="left", va="top", fontsize=10, fontweight="bold", color=INK)
        fig.text(pad_x, 1 - pad_y - 15 / (FIGSIZE[1] * 72),
                 labels["subtitle_index" if as_index else "subtitle_per_million"], ha="left", va="top", color=MUTED)

        if not plotted:
            ax.axis("off")
            ax.text(0.5, 0.5, labels["no_data"], ha="center", va="center", color=MUTED, transform=ax.transAxes)
            fig.savefig(output_path, dpi=PNG_DPI)
            plt.close(fig)
            return

        for color, _, xs, ys in plotted:
            ax.plot(xs, ys, color=color, linewidth=1.8, solid_capstyle="round", zorder=3)
            ax.plot(xs[-1:], ys[-1:], "o", color=color, markersize=3.5, zorder=4)

        all_dates = sorted({d for _, _, xs, _ in plotted for d in xs})
        x_end = _date_axis(ax, all_dates[0], all_dates[-1], lang)
        _value_axis(ax, lang)
        top = max(max(ys) for *_, ys in plotted)
        ax.set_ylim(0, top * 1.22 or 1)
        if as_index:
            ax.axhline(100, color=FAINT, linewidth=0.8, linestyle=(0, (3, 3)), zorder=2)
        _shade_last_12_months(ax, all_dates, x_end, labels)

        peaks = _mark_peaks(ax, plotted, labels, lang)
        names = [label if len(label) <= MAX_LABEL_CHARS else label[: MAX_LABEL_CHARS - 1] + "…"
                 for _, label, _, _ in plotted]
        _fit_layout(fig, ax, names)
        _label_line_ends(fig, ax, plotted, names)
        _drop_colliding(fig, peaks)

        fig.savefig(output_path, dpi=PNG_DPI)
        plt.close(fig)


def _fit_layout(fig, ax, end_label_texts: List[str]) -> None:
    """Sizes the plot area around what's actually drawn -- tick labels on
    the left, end-of-line labels on the right -- instead of fixed margins,
    which either waste width or clip a long label: lay out once with a
    guess, measure how far things stick out, then correct by exactly that."""
    renderer = fig.canvas.get_renderer()
    width_px, height_px = fig.get_size_inches() * fig.dpi
    pt = fig.dpi / 72
    fig.subplots_adjust(left=0.08, right=0.8, top=1 - 40 * pt / height_px, bottom=30 * pt / height_px)
    probes = [
        ax.annotate(text, xy=(1, 0), xycoords="axes fraction", xytext=(END_LABEL_GAP_PT, 0),
                    textcoords="offset points", fontweight="bold", annotation_clip=False)
        for text in end_label_texts
    ]
    fig.canvas.draw()

    pad = FIGURE_PAD_PT * pt
    tick_labels = [t for t in ax.get_yticklabels() if t.get_visible() and t.get_text()]
    overflow_left = pad - min(t.get_window_extent(renderer).x0 for t in tick_labels)
    overflow_right = max(t.get_window_extent(renderer).x1 for t in probes) - (width_px - pad)
    for probe in probes:
        probe.remove()
    box = ax.get_position()
    fig.subplots_adjust(left=box.x0 + overflow_left / width_px, right=box.x1 - overflow_right / width_px)


def _label_line_ends(fig, ax, plotted, names: List[str]) -> None:
    """Names each line just right of its last point, in its own color. When
    ends crowd together, _spread() moves labels apart and a thin leader
    ties each moved label back to its line."""
    box = ax.get_position()
    height_pt, width_pt = box.height * FIGSIZE[1] * 72, box.width * FIGSIZE[0] * 72
    ends = [ax.transLimits.transform((mdates.date2num(xs[-1]), ys[-1]))[1] for _, _, xs, ys in plotted]
    placed = _spread(ends, FONT_SIZE * 1.3 / height_pt, top=1.0)
    for (color, _, xs, ys), name, end, y in zip(plotted, names, ends, placed):
        moved = abs(y - end) * height_pt > 2
        ax.annotate(
            name, xy=(xs[-1], ys[-1]), xytext=(1 + END_LABEL_GAP_PT / width_pt, y), textcoords="axes fraction",
            va="center", ha="left", fontweight="bold", color=color, annotation_clip=False,
            # relpos: the leader leaves from the label's left edge, so it
            # stays in the gap instead of cutting through the labels next to it
            arrowprops=dict(arrowstyle="-", color=color, linewidth=0.6, relpos=(0, 0.5), shrinkA=1, shrinkB=3)
            if moved else None,
        )
