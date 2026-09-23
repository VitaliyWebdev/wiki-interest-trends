from wikitrends.trust import Reason, TrustAssessment, assess_trust, render_reason


def solid_inputs(**overrides):
    """A case that should come out 'high': plenty of history, decent
    volume, a significant trend that survives normalization, and views
    spread out rather than spike-driven."""
    base = dict(
        months_of_data=30,
        avg_monthly_views=250.0,
        mk_p_value=0.01,
        raw_slope_sign=1,
        normalized_slope_sign=1,
        peak_share_top2=0.2,
    )
    base.update(overrides)
    return base


def test_high_trust_when_everything_checks_out():
    result = assess_trust(**solid_inputs())

    assert result.level == "high"
    assert result.reasons  # never an empty explanation, even for "high"


def test_low_trust_with_too_little_history():
    result = assess_trust(**solid_inputs(months_of_data=6))

    assert result.level == "low"
    assert any(r.code == "insufficient_history" and r.params["months"] == 6 for r in result.reasons)


def test_low_trust_with_very_low_view_volume():
    result = assess_trust(**solid_inputs(avg_monthly_views=5.0, months_of_data=30, mk_p_value=0.2))

    assert result.level == "low"


def test_medium_trust_with_exactly_one_concern():
    # everything solid except a series just short of the 24-month bar
    result = assess_trust(**solid_inputs(months_of_data=18))

    assert result.level == "medium"


def test_low_trust_when_trend_reverses_after_normalization():
    result = assess_trust(**solid_inputs(raw_slope_sign=1, normalized_slope_sign=-1))

    assert result.level in ("medium", "low")
    assert any(r.code == "trend_reverses_after_normalization" for r in result.reasons)


def test_low_trust_when_top_two_months_dominate():
    result = assess_trust(**solid_inputs(peak_share_top2=0.8))

    assert any(r.code == "peak_dominated" for r in result.reasons)
    assert result.level in ("medium", "low")


def test_low_trust_when_trend_not_significant():
    result = assess_trust(**solid_inputs(mk_p_value=0.9))

    assert any(r.code == "trend_not_significant" for r in result.reasons)


def test_reasons_always_present_regardless_of_level():
    for level_inputs in [
        solid_inputs(),
        solid_inputs(months_of_data=3),
        solid_inputs(avg_monthly_views=5.0),
    ]:
        result = assess_trust(**level_inputs)
        assert isinstance(result, TrustAssessment)
        assert len(result.reasons) > 0
        for r in result.reasons:
            assert isinstance(r, Reason)


def test_every_reason_says_whether_it_counts_against_the_level():
    # The level is decided by counting concerns (0 -> high, 1 -> medium,
    # 2+ -> low), so the number of flagged reasons must reproduce it --
    # that's what lets report.py mark each reason without re-deriving
    # these rules.
    for inputs, expected_concerns in (
        (solid_inputs(), 0),
        (solid_inputs(mk_p_value=0.2), 1),
        (solid_inputs(mk_p_value=0.2, peak_share_top2=0.8), 2),
        (solid_inputs(months_of_data=6), 1),
    ):
        result = assess_trust(**inputs)
        concerns = [r for r in result.reasons if r.concern]

        assert len(concerns) == expected_concerns, [r.code for r in result.reasons]
    assert all(not r.concern for r in assess_trust(**solid_inputs()).reasons)


def test_a_very_small_p_value_is_shown_as_below_a_threshold_not_as_zero():
    assert "p<0.001" in render_reason(Reason("trend_significant", {"p_value": 0.00002}), "en")
    assert "p=0.007" in render_reason(Reason("trend_significant", {"p_value": 0.0069}), "uk")


def test_render_reason_in_english():
    text = render_reason(Reason("short_history", {"months": 18, "min_months": 24}), lang="en")

    assert text == (
        "Only 18 months of data (24+ needed for a confident year-over-year "
        "comparison of full years)."
    )


def test_render_reason_in_ukrainian():
    text = render_reason(Reason("short_history", {"months": 18, "min_months": 24}), lang="uk")

    assert "18 міс." in text
    assert "24+" in text


def test_render_reason_falls_back_to_english_for_unsupported_language():
    text = render_reason(Reason("trend_significance_unknown"), lang="fr")

    assert text == "Trend significance could not be computed."


def test_every_reason_code_used_by_assess_trust_has_both_uk_and_en_templates():
    # Exercise every branch by running a matrix of inputs, then check
    # every code that came out has both languages -- catches a reason
    # added in English only and forgotten in the templates dict.
    from wikitrends.trust import REASON_TEMPLATES

    seen_codes = set()
    for months in (6, 18, 30):
        for avg in (5.0, 50.0, 200.0):
            for p in (None, 0.9, 0.07, 0.01):
                for signs in ((1, 1), (1, -1), (None, None)):
                    for peak in (None, 0.8, 0.4, 0.1):
                        result = assess_trust(
                            months_of_data=months,
                            avg_monthly_views=avg,
                            mk_p_value=p,
                            raw_slope_sign=signs[0],
                            normalized_slope_sign=signs[1],
                            peak_share_top2=peak,
                        )
                        seen_codes.update(r.code for r in result.reasons)

    assert seen_codes  # sanity: the matrix actually exercised something
    for code in seen_codes:
        assert "en" in REASON_TEMPLATES[code], f"{code} missing an English template"
        assert "uk" in REASON_TEMPLATES[code], f"{code} missing a Ukrainian template"
