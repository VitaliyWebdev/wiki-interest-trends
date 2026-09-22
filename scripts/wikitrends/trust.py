from dataclasses import dataclass
from typing import List, Optional

MIN_MONTHS_FOR_ANY_TREND = 12
MIN_MONTHS_FOR_HIGH = 24

LOW_VOLUME_AVG_VIEWS = 30.0
HIGH_VOLUME_AVG_VIEWS = 100.0

SIGNIFICANCE_ALPHA = 0.05
WEAK_SIGNIFICANCE_ALPHA = 0.10

PEAK_SHARE_HIGH = 0.5
PEAK_SHARE_MODERATE = 0.35


@dataclass
class TrustAssessment:
    level: str  # "high" | "medium" | "low"
    reasons: List[str]


def assess_trust(
    *,
    months_of_data: int,
    avg_monthly_views: float,
    mk_p_value: Optional[float],
    raw_slope_sign: Optional[int],
    normalized_slope_sign: Optional[int],
    peak_share_top2: Optional[float],
) -> TrustAssessment:
    """Deterministic high/medium/low rule -- this is a rule in code, not a
    judgment call for the calling model to make. Every branch appends a
    human-readable reason, on both the "this is fine" and "this is a
    concern" side, so the level always comes with an explanation, not just
    a label. Level is decided purely by counting concerns: 0 -> high,
    1 -> medium, 2+ -> low. See docs/dev/stats-and-trust.md for the
    reasoning behind the thresholds."""
    if months_of_data < MIN_MONTHS_FOR_ANY_TREND:
        return TrustAssessment(
            level="low",
            reasons=[
                f"Only {months_of_data} months of data -- need at least "
                f"{MIN_MONTHS_FOR_ANY_TREND} to say anything about a trend at all."
            ],
        )

    concerns: List[str] = []
    strengths: List[str] = []

    if months_of_data < MIN_MONTHS_FOR_HIGH:
        concerns.append(
            f"Only {months_of_data} months of data ({MIN_MONTHS_FOR_HIGH}+ needed "
            "for a confident year-over-year comparison of full years)."
        )
    else:
        strengths.append(f"{months_of_data} months of data -- enough to compare full years.")

    if avg_monthly_views < LOW_VOLUME_AVG_VIEWS:
        concerns.append(
            f"Average of {avg_monthly_views:.0f} views/month is low -- small "
            "numbers are noisy, month-to-month swings can look like a trend."
        )
    elif avg_monthly_views < HIGH_VOLUME_AVG_VIEWS:
        concerns.append(
            f"Average of {avg_monthly_views:.0f} views/month is moderate -- "
            "more views would make the trend more reliable."
        )
    else:
        strengths.append(
            f"Average of {avg_monthly_views:.0f} views/month -- enough volume "
            "that month-to-month noise is less of a concern."
        )

    if mk_p_value is None:
        concerns.append("Trend significance could not be computed.")
    elif mk_p_value >= WEAK_SIGNIFICANCE_ALPHA:
        concerns.append(f"Trend is not statistically significant (Mann-Kendall p={mk_p_value:.2f}).")
    elif mk_p_value >= SIGNIFICANCE_ALPHA:
        concerns.append(f"Trend is only weakly significant (Mann-Kendall p={mk_p_value:.2f}).")
    else:
        strengths.append(f"Trend is statistically significant (Mann-Kendall p={mk_p_value:.3f}).")

    if raw_slope_sign is not None and normalized_slope_sign is not None:
        if raw_slope_sign != normalized_slope_sign:
            concerns.append(
                "Trend direction changes after normalizing for the language "
                "edition's overall traffic -- the raw trend may just be "
                "tracking Wikipedia's own growth or decline, not real interest "
                "in the topic."
            )
        else:
            strengths.append(
                "Trend direction holds after normalizing for the language "
                "edition's overall traffic."
            )

    if peak_share_top2 is not None:
        if peak_share_top2 >= PEAK_SHARE_HIGH:
            concerns.append(
                f"The top 2 months alone account for {peak_share_top2:.0%} of all "
                "views -- this may be a news spike, not sustained interest."
            )
        elif peak_share_top2 >= PEAK_SHARE_MODERATE:
            concerns.append(
                f"The top 2 months account for {peak_share_top2:.0%} of all views -- "
                "some concentration in short spikes."
            )
        else:
            strengths.append(
                f"Views are spread out over time (top 2 months are only "
                f"{peak_share_top2:.0%} of the total), not driven by a single spike."
            )

    if not concerns:
        level = "high"
    elif len(concerns) == 1:
        level = "medium"
    else:
        level = "low"

    return TrustAssessment(level=level, reasons=strengths + concerns)
