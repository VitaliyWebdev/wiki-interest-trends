import matplotlib.axes

from wikitrends.chart import CHART_LABELS, render_chart


def point(timestamp, per_million):
    # Same shape as analysis.json's series[].normalized entries.
    return {"timestamp": timestamp, "views": 1, "project_total": 1, "per_million": per_million}


def test_render_chart_creates_a_valid_png(tmp_path):
    output = tmp_path / "chart.png"
    series = {"topic A (uk)": [point("2024010100", 100.0), point("2024020100", 300.0)]}

    render_chart(series, output)

    assert output.exists()
    assert output.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_render_chart_creates_missing_parent_directories(tmp_path):
    output = tmp_path / "nested" / "dir" / "chart.png"

    render_chart({"a": [point("2024010100", 10000.0)]}, output)

    assert output.exists()


def test_render_chart_handles_multiple_series(tmp_path):
    output = tmp_path / "chart.png"
    series = {
        "topic A (pl)": [point("2024010100", 10.0), point("2024020100", 20.0)],
        "topic A (cs)": [point("2024010100", 10.0), point("2024020100", 30.0)],
    }

    render_chart(series, output)

    assert output.exists()


def test_render_chart_handles_empty_series_without_crashing(tmp_path):
    output = tmp_path / "chart.png"

    render_chart({}, output)

    assert output.exists()


def test_render_chart_skips_a_label_with_no_points(tmp_path):
    output = tmp_path / "chart.png"
    series = {"empty": [], "has data": [point("2024010100", 10000.0)]}

    render_chart(series, output)

    assert output.exists()


def test_render_chart_uses_labels_in_the_requested_language(tmp_path, monkeypatch):
    # The chart is embedded in the PDF as an image, so its text can't be
    # checked by extracting PDF text -- capture what's drawn instead.
    drawn = []
    for method in ("set_title", "set_ylabel", "annotate"):
        original = getattr(matplotlib.axes.Axes, method)

        def spy(self, text, *args, _original=original, **kwargs):
            drawn.append(text)
            return _original(self, text, *args, **kwargs)

        monkeypatch.setattr(matplotlib.axes.Axes, method, spy)

    render_chart({"Астрономія (uk)": [point("2024010100", 5.0)]}, tmp_path / "c.png", lang="uk")

    uk = CHART_LABELS["uk"]
    assert uk["title"] in drawn
    assert uk["ylabel"] in drawn
    assert uk["peak"] in drawn
    assert CHART_LABELS["en"]["ylabel"] not in drawn
