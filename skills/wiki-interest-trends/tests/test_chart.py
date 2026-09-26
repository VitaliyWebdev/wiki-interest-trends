import matplotlib.axes
from pypdf import PdfReader

from wikitrends.chart import CHART_LABELS, _as_index, _spread, render_chart


def point(timestamp, per_million):
    # Same shape as analysis.json's series[].normalized entries.
    return {"timestamp": timestamp, "views": 1, "project_total": 1, "per_million": per_million}


def months(n, start_year=2024, value=lambda i: 10.0 + i):
    return [point(f"{start_year + i // 12}{i % 12 + 1:02d}0100", value(i)) for i in range(n)]


def chart_text(tmp_path, series, lang="en"):
    # Rendered as PDF, the chart's text is real text (pdf.fonttype 42),
    # so what's drawn can be read back exactly as a reader would see it.
    output = tmp_path / "chart.pdf"
    render_chart(series, output, lang=lang)
    return PdfReader(str(output)).pages[0].extract_text()


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


def test_render_chart_draws_every_label_in_the_requested_language(tmp_path):
    peak_in_aug_2025 = months(24, value=lambda i: 50.0 if i == 19 else 10.0)
    text = chart_text(tmp_path, {"Астрономія (uk)": peak_in_aug_2025}, lang="uk")

    uk = CHART_LABELS["uk"]
    assert uk["title"] in text
    assert uk["subtitle_per_million"] in text
    assert uk["last_12"] in text
    assert f"{uk['peak']} · серп. 2025" in text  # the peak's month, named in Ukrainian
    assert "січ." in text  # the date axis too, not strftime's English
    assert "Астрономія (uk)" in text  # labeled at the line's end...
    assert CHART_LABELS["en"]["title"] not in text


def test_render_chart_labels_line_ends_instead_of_drawing_a_legend(tmp_path, monkeypatch):
    # A legend used to sit on top of the data it described.
    legends = []
    monkeypatch.setattr(matplotlib.axes.Axes, "legend", lambda self, *a, **kw: legends.append(a))

    text = chart_text(tmp_path, {"A (en)": months(3), "B (uk)": months(3)})

    assert legends == []
    assert "A (en)" in text and "B (uk)" in text


def test_one_series_is_drawn_in_views_per_million_several_as_an_index(tmp_path):
    single = chart_text(tmp_path, {"A (en)": months(3)})
    several = chart_text(tmp_path, {"A (en)": months(3), "B (uk)": months(3)})

    assert CHART_LABELS["en"]["subtitle_per_million"] in single
    assert CHART_LABELS["en"]["subtitle_index"] in several


def test_last_12_months_are_shaded_only_when_there_is_a_year_to_compare_them_with(tmp_path):
    # Shading marks the window YoY compares, which needs 24 months.
    assert CHART_LABELS["en"]["last_12"] in chart_text(tmp_path, {"A": months(24)})
    assert CHART_LABELS["en"]["last_12"] not in chart_text(tmp_path, {"A": months(23)})


def test_as_index_rebases_a_series_to_100_at_its_own_average():
    assert _as_index([5.0, 10.0, 15.0]) == [50.0, 100.0, 150.0]
    assert _as_index([0.0, 0.0]) == [0.0, 0.0]


def test_spread_pushes_overlapping_labels_apart_and_keeps_their_order():
    spread = _spread([0.50, 0.51, 0.90], min_gap=0.05, top=1.0)

    assert spread[0] == 0.50
    assert spread[1] >= spread[0] + 0.05 - 1e-9
    assert spread[2] == 0.90  # far enough already, left where it is


def test_spread_pushes_labels_back_down_from_the_top_edge():
    spread = _spread([0.98, 0.99], min_gap=0.05, top=1.0)

    assert spread[1] == 1.0
    assert abs(spread[0] - 0.95) < 1e-9


def fonts_used(pdf_path):
    """{character: BaseFont} for every non-ASCII character drawn."""
    used = {}

    def visit(text, cm, tm, font, size):
        for ch in text:
            if ord(ch) > 0x7F and font:
                used[ch] = font["/BaseFont"].split("+")[-1]

    PdfReader(str(pdf_path)).pages[0].extract_text(visitor_text=visit)
    return used


def test_chinese_japanese_and_korean_labels_are_drawn_in_fonts_that_have_them(tmp_path):
    # DejaVu Sans has no CJK: these titles used to print as empty boxes.
    import warnings

    output = tmp_path / "chart.pdf"
    with warnings.catch_warnings():
        warnings.simplefilter("error")  # matplotlib warns "Glyph ... missing from font(s)"
        render_chart({"天文学 (ja)": months(3), "间歇性断食 (zh)": months(3), "천문학 (ko)": months(3)}, output)

    used = fonts_used(output)
    assert {used[ch] for ch in "天文学间歇性断食"} == {"DroidSansFallback"}
    assert {used[ch] for ch in "천문학"} == {"NanumGothic"}


def test_hangul_syllables_are_not_split_into_jamo(tmp_path):
    # With Droid Sans Fallback ahead of NanumGothic, matplotlib decomposed
    # 간 into 가 + ᆫ and drew the jamo from Droid: "가ㄴ헐적" on the chart.
    # The extracted text still reads "간", so check the font instead.
    output = tmp_path / "chart.pdf"
    render_chart({"간헐적 단식 (ko)": months(3)}, output)

    used = fonts_used(output)
    assert {used[ch] for ch in "간헐적단식"} == {"NanumGothic"}
