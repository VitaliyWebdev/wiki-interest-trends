import math

import pytest

from wikitrends.pageviews import MonthlyPoint
from wikitrends.stats import (
    MannKendallResult,
    average_monthly_views,
    mann_kendall_test,
    peak_share,
    seasonality_ratio,
    theil_sen_log_slope,
    year_over_year_growth,
)


def test_yoy_growth_computes_ratio_between_two_12_month_sums():
    # first 12 months at 100/mo (total 1200), next 12 at 150/mo (total 1800)
    values = [100.0] * 12 + [150.0] * 12
    assert year_over_year_growth(values) == pytest.approx(0.5)


def test_yoy_growth_none_with_fewer_than_24_months():
    assert year_over_year_growth([100.0] * 23) is None


def test_yoy_growth_none_when_previous_period_is_zero():
    values = [0.0] * 12 + [100.0] * 12
    assert year_over_year_growth(values) is None


def test_theil_sen_recovers_exact_slope_of_perfect_exponential_growth():
    # views = 2**i -> log(views) increases by exactly ln(2) each step
    values = [float(2**i) for i in range(6)]
    slope = theil_sen_log_slope(values)
    assert slope == pytest.approx(math.log(2))


def test_theil_sen_is_robust_to_a_single_huge_outlier():
    # same perfect series, but the last point is a 1,000,000-view spike.
    # Theil-Sen (median of pairwise slopes) should shrug it off; a mean-based
    # slope would not (verified separately: OLS jumps from ln(2)=0.69 to 2.17).
    values = [float(2**i) for i in range(5)] + [1_000_000.0]
    slope = theil_sen_log_slope(values)
    assert slope == pytest.approx(math.log(2))


def test_theil_sen_none_when_only_one_month_has_views():
    assert theil_sen_log_slope([0.0, 0.0, 5.0]) is None


def test_theil_sen_none_for_a_single_point_series():
    assert theil_sen_log_slope([5.0]) is None


def test_theil_sen_ignores_zero_view_months_when_taking_the_log():
    values = [0.0, 1.0, 2.0, 4.0]
    # dropping the zero, months at index 1,2,3 have log-values 0, ln2, ln4
    # which is still a perfect ln(2)-per-step series
    slope = theil_sen_log_slope(values)
    assert slope == pytest.approx(math.log(2))


def test_mann_kendall_strictly_increasing_series():
    result = mann_kendall_test([float(i) for i in range(1, 25)])

    assert result == MannKendallResult(trend="increasing", p_value=pytest.approx(9.027667502436998e-12), s_statistic=276)


def test_mann_kendall_strictly_decreasing_series():
    result = mann_kendall_test([float(i) for i in range(24, 0, -1)])

    assert result.trend == "decreasing"
    assert result.s_statistic == -276
    assert result.p_value == pytest.approx(9.027667502436998e-12)


def test_mann_kendall_constant_series_is_no_trend():
    result = mann_kendall_test([50.0] * 24)

    assert result == MannKendallResult(trend="no trend", p_value=1.0, s_statistic=0)


def test_mann_kendall_alternating_series_is_no_trend():
    values = [10.0, 5.0] * 12
    result = mann_kendall_test(values)

    assert result.trend == "no trend"
    assert result.s_statistic == -12
    assert result.p_value == pytest.approx(0.750831884089117)


def test_peak_share_two_dominant_months():
    # total = 1000, top 2 months (900, 50) = 950 -> 95%
    values = [900.0, 50.0, 10.0, 10.0, 10.0, 10.0, 10.0]
    assert peak_share(values, top_n=2) == pytest.approx(950.0 / 1000.0)


def test_peak_share_evenly_spread_views():
    values = [100.0] * 10
    # top 2 of 10 equal months = 200/1000 = 20%
    assert peak_share(values, top_n=2) == pytest.approx(0.2)


def test_peak_share_none_for_empty_series():
    assert peak_share([]) is None


def test_average_monthly_views():
    assert average_monthly_views([100.0, 200.0, 300.0]) == pytest.approx(200.0)


def test_average_monthly_views_zero_for_empty_series():
    assert average_monthly_views([]) == 0.0


def test_seasonality_ratio_detects_a_strong_seasonal_pattern():
    # 2 full years: January always spikes to 1000, every other month is 100
    points = []
    for year in (2022, 2023):
        for month in range(1, 13):
            views = 1000 if month == 1 else 100
            points.append(MonthlyPoint(f"{year}{month:02d}0100", views))

    ratio = seasonality_ratio(points)

    assert ratio == pytest.approx(10.0)  # 1000 / 100


def test_seasonality_ratio_is_one_for_a_perfectly_flat_series():
    points = [
        MonthlyPoint(f"2022{month:02d}0100", 100) for month in range(1, 13)
    ] + [MonthlyPoint(f"2023{month:02d}0100", 100) for month in range(1, 13)]

    assert seasonality_ratio(points) == pytest.approx(1.0)


def test_seasonality_ratio_none_with_fewer_than_24_months():
    points = [MonthlyPoint(f"2023{month:02d}0100", 100) for month in range(1, 13)]

    assert seasonality_ratio(points) is None
