from dataclasses import dataclass, field, replace
from typing import Any, Dict, List, Optional

from .i18n import DEFAULT_LANG, pick

MIN_MONTHS_FOR_ANY_TREND = 12
MIN_MONTHS_FOR_HIGH = 24

LOW_VOLUME_AVG_VIEWS = 30.0
HIGH_VOLUME_AVG_VIEWS = 100.0

SIGNIFICANCE_ALPHA = 0.05
WEAK_SIGNIFICANCE_ALPHA = 0.10

PEAK_SHARE_HIGH = 0.5
PEAK_SHARE_MODERATE = 0.35

# Reasons are code+params, not pre-formatted strings, specifically so a
# report can render them in the user's language (uk/en at minimum, per the
# spec) instead of always English -- a real gap found running report.py
# end-to-end: a Ukrainian-language report had every other section in
# Ukrainian except this list, which was hardcoded English text.
REASON_TEMPLATES: Dict[str, Dict[str, str]] = {
    "insufficient_history": {
        "en": "Only {months} months of data -- need at least {min_months} to say anything about a trend at all.",
        "uk": "Лише {months} міс. даних — потрібно щонайменше {min_months}, щоб взагалі говорити про тренд.",
    },
    "short_history": {
        "en": "Only {months} months of data ({min_months}+ needed for a confident year-over-year comparison of full years).",
        "uk": "Лише {months} міс. даних (потрібно {min_months}+ для впевненого порівняння повних років).",
    },
    "long_history": {
        "en": "{months} months of data -- enough to compare full years.",
        "uk": "{months} міс. даних — достатньо для порівняння повних років.",
    },
    "low_volume": {
        "en": "Average of {avg_views:.0f} views/month is low -- small numbers are noisy, month-to-month swings can look like a trend.",
        "uk": "У середньому {avg_views:.0f} переглядів/міс — це мало, малі числа шумні, місячні коливання можуть виглядати як тренд.",
    },
    "moderate_volume": {
        "en": "Average of {avg_views:.0f} views/month is moderate -- more views would make the trend more reliable.",
        "uk": "У середньому {avg_views:.0f} переглядів/міс — помірно, більше переглядів зробило б тренд надійнішим.",
    },
    "high_volume": {
        "en": "Average of {avg_views:.0f} views/month -- enough volume that month-to-month noise is less of a concern.",
        "uk": "У середньому {avg_views:.0f} переглядів/міс — достатній обсяг, щоб місячний шум менше турбував.",
    },
    "trend_significance_unknown": {
        "en": "Trend significance could not be computed.",
        "uk": "Не вдалося обчислити значущість тренду.",
    },
    "trend_not_significant": {
        "en": "Trend is not statistically significant (Mann-Kendall p={p_value:.2f}).",
        "uk": "Тренд статистично незначущий (Mann-Kendall p={p_value:.2f}).",
    },
    "trend_weakly_significant": {
        "en": "Trend is only weakly significant (Mann-Kendall p={p_value:.2f}).",
        "uk": "Тренд лише слабко значущий (Mann-Kendall p={p_value:.2f}).",
    },
    "trend_significant": {
        "en": "Trend is statistically significant (Mann-Kendall {p}).",
        "uk": "Тренд статистично значущий (Mann-Kendall {p}).",
    },
    "trend_reverses_after_normalization": {
        "en": "Trend direction changes after normalizing for the language edition's overall traffic -- the raw trend may just be tracking Wikipedia's own growth or decline, not real interest in the topic.",
        "uk": "Напрям тренду змінюється після нормалізації на загальний трафік мовного розділу — сирий тренд може відображати зростання чи спад самої Вікіпедії, а не реальний інтерес до теми.",
    },
    "trend_holds_after_normalization": {
        "en": "Trend direction holds after normalizing for the language edition's overall traffic.",
        "uk": "Напрям тренду зберігається після нормалізації на загальний трафік мовного розділу.",
    },
    "peak_dominated": {
        "en": "The top 2 months alone account for {peak_share:.0%} of all views -- this may be a news spike, not sustained interest.",
        "uk": "Лише 2 найпіковіші місяці дають {peak_share:.0%} усіх переглядів — це може бути новинний сплеск, а не стійкий інтерес.",
    },
    "peak_moderate": {
        "en": "The top 2 months account for {peak_share:.0%} of all views -- some concentration in short spikes.",
        "uk": "2 найпіковіші місяці дають {peak_share:.0%} усіх переглядів — певна концентрація в коротких сплесках.",
    },
    "spread_out": {
        "en": "Views are spread out over time (top 2 months are only {peak_share:.0%} of the total), not driven by a single spike.",
        "uk": "Перегляди рівномірно розподілені в часі (2 найпіковіші місяці — лише {peak_share:.0%} від загалу), не спричинені одним сплеском.",
    },
}


@dataclass
class Reason:
    code: str
    params: Dict[str, Any] = field(default_factory=dict)
    # True if this reason counts against the trust level, False if it
    # supports it -- so a report can mark each one without re-deriving
    # assess_trust()'s rules.
    concern: bool = False

    def render(self, lang: str = DEFAULT_LANG) -> str:
        return render_reason(self, lang)


def render_reason(reason: Reason, lang: str = DEFAULT_LANG) -> str:
    templates = REASON_TEMPLATES.get(reason.code)
    if not templates:
        return reason.code
    params = dict(reason.params)
    if params.get("p_value") is not None:
        # A strong trend's p rounds to "p=0.000", which reads as "impossible".
        params["p"] = "p<0.001" if params["p_value"] < 0.001 else f"p={params['p_value']:.3f}"
    return pick(templates, lang).format(**params)


@dataclass
class TrustAssessment:
    level: str  # "high" | "medium" | "low"
    reasons: List[Reason]


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
    reason, on both the "this is fine" and "this is a concern" side, so the
    level always comes with an explanation, not just a label. Level is
    decided purely by counting concerns: 0 -> high, 1 -> medium, 2+ -> low.
    See docs/dev/stats-and-trust.md for the reasoning behind the
    thresholds."""
    if months_of_data < MIN_MONTHS_FOR_ANY_TREND:
        return TrustAssessment(
            level="low",
            reasons=[
                Reason(
                    "insufficient_history",
                    {"months": months_of_data, "min_months": MIN_MONTHS_FOR_ANY_TREND},
                    concern=True,
                )
            ],
        )

    concerns: List[Reason] = []
    strengths: List[Reason] = []

    if months_of_data < MIN_MONTHS_FOR_HIGH:
        concerns.append(
            Reason("short_history", {"months": months_of_data, "min_months": MIN_MONTHS_FOR_HIGH})
        )
    else:
        strengths.append(Reason("long_history", {"months": months_of_data}))

    if avg_monthly_views < LOW_VOLUME_AVG_VIEWS:
        concerns.append(Reason("low_volume", {"avg_views": avg_monthly_views}))
    elif avg_monthly_views < HIGH_VOLUME_AVG_VIEWS:
        concerns.append(Reason("moderate_volume", {"avg_views": avg_monthly_views}))
    else:
        strengths.append(Reason("high_volume", {"avg_views": avg_monthly_views}))

    if mk_p_value is None:
        concerns.append(Reason("trend_significance_unknown"))
    elif mk_p_value >= WEAK_SIGNIFICANCE_ALPHA:
        concerns.append(Reason("trend_not_significant", {"p_value": mk_p_value}))
    elif mk_p_value >= SIGNIFICANCE_ALPHA:
        concerns.append(Reason("trend_weakly_significant", {"p_value": mk_p_value}))
    else:
        strengths.append(Reason("trend_significant", {"p_value": mk_p_value}))

    if raw_slope_sign is not None and normalized_slope_sign is not None:
        if raw_slope_sign != normalized_slope_sign:
            concerns.append(Reason("trend_reverses_after_normalization"))
        else:
            strengths.append(Reason("trend_holds_after_normalization"))

    if peak_share_top2 is not None:
        if peak_share_top2 >= PEAK_SHARE_HIGH:
            concerns.append(Reason("peak_dominated", {"peak_share": peak_share_top2}))
        elif peak_share_top2 >= PEAK_SHARE_MODERATE:
            concerns.append(Reason("peak_moderate", {"peak_share": peak_share_top2}))
        else:
            strengths.append(Reason("spread_out", {"peak_share": peak_share_top2}))

    if not concerns:
        level = "high"
    elif len(concerns) == 1:
        level = "medium"
    else:
        level = "low"

    return TrustAssessment(level=level, reasons=strengths + [replace(r, concern=True) for r in concerns])
