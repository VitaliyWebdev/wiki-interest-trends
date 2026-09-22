import math
from collections import Counter
from dataclasses import dataclass
from typing import List, Optional

from .pageviews import MonthlyPoint


@dataclass
class MannKendallResult:
    trend: str  # "increasing" | "decreasing" | "no trend"
    p_value: float
    s_statistic: int


def year_over_year_growth(values: List[float]) -> Optional[float]:
    """Growth of the most recent 12 months' total vs. the 12 months before
    that, as a ratio (0.5 = +50%). This sums whole years specifically to
    cancel out seasonality, which a month-over-month comparison would not.
    None if there's under 24 months of contiguous monthly data, or if the
    earlier 12-month total is 0 (growth from zero is undefined, not
    infinite)."""
    if len(values) < 24:
        return None
    recent = sum(values[-12:])
    previous = sum(values[-24:-12])
    if previous == 0:
        return None
    return (recent - previous) / previous


def theil_sen_log_slope(values: List[float]) -> Optional[float]:
    """Theil-Sen slope (median of all pairwise slopes) of log(views) against
    month index. Robust to a handful of outlier months in a way a
    least-squares slope isn't -- see docs/dev/stats-and-trust.md for a
    worked comparison. Months with 0 views are dropped (log undefined at 0)
    rather than treated as errors; a topic can genuinely have zero-view
    months. None if fewer than 2 months have data."""
    xs = []
    ys = []
    for i, v in enumerate(values):
        if v > 0:
            xs.append(i)
            ys.append(math.log(v))
    n = len(xs)
    if n < 2:
        return None

    slopes = []
    for i in range(n):
        for j in range(i + 1, n):
            dx = xs[j] - xs[i]
            slopes.append((ys[j] - ys[i]) / dx)
    slopes.sort()
    mid = len(slopes) // 2
    if len(slopes) % 2:
        return slopes[mid]
    return (slopes[mid - 1] + slopes[mid]) / 2


def _normal_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def mann_kendall_test(values: List[float], alpha: float = 0.05) -> MannKendallResult:
    """Mann-Kendall trend test with the standard tie correction (low-traffic
    series have lots of repeated small integers, so ties are the common
    case, not an edge case). Returns the trend classification at the given
    significance level plus the raw S statistic and two-tailed p-value, so
    callers/tests can inspect the evidence, not just the verdict."""
    n = len(values)
    if n < 2:
        return MannKendallResult(trend="no trend", p_value=1.0, s_statistic=0)

    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            diff = values[j] - values[i]
            s += (diff > 0) - (diff < 0)

    tie_counts = Counter(values)
    tie_term = sum(t * (t - 1) * (2 * t + 5) for t in tie_counts.values() if t > 1)
    var_s = (n * (n - 1) * (2 * n + 5) - tie_term) / 18

    if var_s <= 0:
        z = 0.0
    elif s > 0:
        z = (s - 1) / math.sqrt(var_s)
    elif s < 0:
        z = (s + 1) / math.sqrt(var_s)
    else:
        z = 0.0

    p_value = 2 * (1 - _normal_cdf(abs(z)))

    if p_value < alpha and s > 0:
        trend = "increasing"
    elif p_value < alpha and s < 0:
        trend = "decreasing"
    else:
        trend = "no trend"

    return MannKendallResult(trend=trend, p_value=p_value, s_statistic=s)


def peak_share(values: List[float], top_n: int = 2) -> Optional[float]:
    """Fraction of total views contributed by the top_n highest months --
    a high share means the trend may be a news spike, not sustained
    interest. None for an empty or all-zero series (share is undefined,
    not zero)."""
    if not values:
        return None
    total = sum(values)
    if total == 0:
        return None
    top = sorted(values, reverse=True)[:top_n]
    return sum(top) / total


def average_monthly_views(values: List[float]) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)


def seasonality_ratio(points: List[MonthlyPoint]) -> Optional[float]:
    """Ratio of the highest-average calendar month to the lowest-average
    calendar month (e.g. 10.0 means the peak month averages 10x the quiet
    month). None with under 24 months: with only one sample per calendar
    month there's no way to tell a seasonal pattern from a one-off spike in
    that particular month."""
    if len(points) < 24:
        return None
    by_month: dict = {}
    for p in points:
        month = int(p.timestamp[4:6])
        by_month.setdefault(month, []).append(p.views)
    if len(by_month) < 12:
        return None
    averages = [sum(v) / len(v) for v in by_month.values()]
    lo, hi = min(averages), max(averages)
    if lo == 0:
        return None
    return hi / lo
