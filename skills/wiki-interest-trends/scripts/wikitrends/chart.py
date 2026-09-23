from datetime import date
from pathlib import Path
from typing import Any, Dict, List

import matplotlib

matplotlib.use("Agg")  # headless: this always runs from a CLI script, never a GUI
import matplotlib.pyplot as plt

from .i18n import DEFAULT_LANG, pick

CHART_LABELS: Dict[str, Dict[str, str]] = {
    "en": {
        "title": "Wikipedia pageview trend",
        "ylabel": "views per million project views",
        "peak": "peak",
    },
    "uk": {
        "title": "Динаміка переглядів у Wikipedia",
        "ylabel": "перегляди на мільйон переглядів розділу",
        "peak": "пік",
    },
}


def _timestamp_to_date(timestamp: str) -> date:
    return date(int(timestamp[0:4]), int(timestamp[4:6]), int(timestamp[6:8]))


def render_chart(
    series_by_label: Dict[str, List[Dict[str, Any]]], output_path: Path, lang: str = DEFAULT_LANG
) -> None:
    """One PNG: normalized views-per-million over time, one line per label
    (a "topic (language)" combination), each series's own peak month
    marked. Points are analysis.json's series[].normalized entries, so
    analyze.py and report.py draw from the exact same data. A label with no
    points is skipped rather than erroring -- it just means that
    topic/language pair had no data, which analyze.py already reports
    separately."""
    labels = pick(CHART_LABELS, lang)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(9, 4.5), dpi=150)

    plotted_anything = False
    for label, points in series_by_label.items():
        if not points:
            continue
        plotted_anything = True
        xs = [_timestamp_to_date(p["timestamp"]) for p in points]
        ys = [p["per_million"] for p in points]
        (line,) = ax.plot(xs, ys, marker="o", markersize=3, label=label)

        peak = max(points, key=lambda p: p["per_million"])
        ax.annotate(
            labels["peak"],
            xy=(_timestamp_to_date(peak["timestamp"]), peak["per_million"]),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=8,
            color=line.get_color(),
        )

    ax.set_title(labels["title"])
    ax.set_ylabel(labels["ylabel"])
    if plotted_anything:
        ax.legend(loc="upper left", fontsize=8)
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(output_path)
    plt.close(fig)
