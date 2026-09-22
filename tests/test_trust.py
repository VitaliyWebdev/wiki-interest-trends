from wikitrends.trust import TrustAssessment, assess_trust


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
    assert any("6 months" in r for r in result.reasons)


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
    assert any("normaliz" in r.lower() for r in result.reasons)


def test_low_trust_when_top_two_months_dominate():
    result = assess_trust(**solid_inputs(peak_share_top2=0.8))

    assert any("top 2 months" in r for r in result.reasons)
    assert result.level in ("medium", "low")


def test_low_trust_when_trend_not_significant():
    result = assess_trust(**solid_inputs(mk_p_value=0.9))

    assert any("not statistically significant" in r for r in result.reasons)


def test_reasons_always_present_regardless_of_level():
    for level_inputs in [
        solid_inputs(),
        solid_inputs(months_of_data=3),
        solid_inputs(avg_monthly_views=5.0),
    ]:
        result = assess_trust(**level_inputs)
        assert isinstance(result, TrustAssessment)
        assert len(result.reasons) > 0
