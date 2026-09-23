"""Design tokens shared by chart.py and report.py, so a series is the same
color on the chart line, its KPI card and its table sparkline -- which is
what lets the report drop the chart legend entirely.

Hex strings only: both matplotlib and reportlab (`colors.HexColor`) take
them, and neither library has to be imported here."""
from typing import List

INK = "#111827"  # body text
MUTED = "#6B7280"  # secondary text, axis labels
FAINT = "#9CA3AF"  # tertiary text, ticks
RULE = "#E5E7EB"  # hairlines, gridlines
SURFACE = "#F3F4F6"  # card backgrounds, the chart's last-12-months band
ACCENT = "#0072B2"
ACCENT_TINT = "#EAF2F8"  # the conclusion callout's background

# Okabe-Ito, in its recommended order (blue, orange first): stays
# distinguishable under every common color-vision deficiency. Its yellow
# (#F0E442) is left out -- too faint for thin lines on white.
SERIES_COLORS: List[str] = ["#0072B2", "#E69F00", "#009E73", "#CC79A7", "#56B4E9", "#D55E00", "#000000"]

# Direction of change. Never the only cue: every colored number also
# carries its sign and an arrow, for readers who can't tell these apart.
UP = "#1A7F37"
DOWN = "#C62828"
FLAT = MUTED

TRUST_COLORS = {"high": UP, "medium": "#B45309", "low": DOWN}


def series_color(index: int) -> str:
    return SERIES_COLORS[index % len(SERIES_COLORS)]
