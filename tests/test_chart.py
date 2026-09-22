from wikitrends.chart import render_chart
from wikitrends.pageviews import NormalizedPoint


def test_render_chart_creates_a_valid_png(tmp_path):
    output = tmp_path / "chart.png"
    series = {
        "topic A (uk)": [
            NormalizedPoint("2024010100", 100, 1_000_000, 100.0),
            NormalizedPoint("2024020100", 300, 1_000_000, 300.0),
        ]
    }

    render_chart(series, output, title="Test chart")

    assert output.exists()
    assert output.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_chart_creates_missing_parent_directories(tmp_path):
    output = tmp_path / "nested" / "dir" / "chart.png"
    series = {"a": [NormalizedPoint("2024010100", 1, 100, 10000.0)]}

    render_chart(series, output, title="Test chart")

    assert output.exists()


def test_render_chart_handles_multiple_series(tmp_path):
    output = tmp_path / "chart.png"
    series = {
        "topic A (pl)": [
            NormalizedPoint("2024010100", 10, 1_000_000, 10.0),
            NormalizedPoint("2024020100", 20, 1_000_000, 20.0),
        ],
        "topic A (cs)": [
            NormalizedPoint("2024010100", 5, 500_000, 10.0),
            NormalizedPoint("2024020100", 15, 500_000, 30.0),
        ],
    }

    render_chart(series, output, title="Comparison")

    assert output.exists()


def test_render_chart_handles_empty_series_without_crashing(tmp_path):
    output = tmp_path / "chart.png"

    render_chart({}, output, title="Nothing to show")

    assert output.exists()


def test_render_chart_skips_a_label_with_no_points(tmp_path):
    output = tmp_path / "chart.png"
    series = {
        "empty": [],
        "has data": [NormalizedPoint("2024010100", 1, 100, 10000.0)],
    }

    render_chart(series, output, title="Mixed")

    assert output.exists()
