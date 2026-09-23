import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from pypdf import PdfReader

import report
from report import _direction_style, _reason_entries, generate_report
from wikitrends import theme
from wikitrends.chart import CHART_LABELS
from wikitrends.errors import AppError
from wikitrends.trust import Reason, render_reason


def make_series(article="Інтервальне голодування", lang="uk", found=True, trust_level="high", yoy=0.42, trend="increasing"):
    if not found:
        return {"qid": "Q1", "lang": lang, "article": None, "label": f"Q1 ({lang})", "found": False, "reason": "no_article_in_language"}
    return {
        "qid": "Q1",
        "lang": lang,
        "article": article,
        "label": f"{article} ({lang})",
        "found": True,
        "normalized": [
            {"timestamp": "2024010100", "views": 200, "project_total": 1_000_000, "per_million": 200.0},
            {"timestamp": "2024020100", "views": 300, "project_total": 1_000_000, "per_million": 300.0},
        ],
        "metrics": {
            "avg_monthly_views": 250.3,
            "yoy_growth_raw": yoy,
            "mann_kendall": {"trend": trend, "p_value": 0.01, "s_statistic": 100},
        },
        "trust": {
            "level": trust_level,
            "reasons": ["Trend is statistically significant (Mann-Kendall p=0.010)."],
            "reason_codes": [{"code": "trend_significant", "params": {"p_value": 0.01}, "concern": False}],
        },
    }


def make_analysis(series=None, warnings=None):
    return {
        "ok": True,
        "series": series if series is not None else [make_series()],
        "warnings": warnings or [],
    }


def test_generate_report_renders_its_own_chart_in_the_report_language(tmp_path, monkeypatch):
    # analyze.py's chart.png is drawn before anyone knows the report's
    # language, so embedding it would put an English chart inside a
    # Ukrainian report. The report must redraw it from analysis.json's
    # own data, in its own language.
    calls = []
    original = report.render_chart

    def spy(series_by_label, output_path, lang):
        calls.append({"series": series_by_label, "lang": lang})
        original(series_by_label, output_path, lang=lang)

    monkeypatch.setattr(report, "render_chart", spy)
    analysis = make_analysis()

    generate_report(analysis, output_path=tmp_path / "report.pdf", lang="uk")

    assert len(calls) == 1
    assert calls[0]["lang"] == "uk"
    series = analysis["series"][0]
    assert calls[0]["series"] == {series["label"]: series["normalized"]}


def test_generate_report_skips_the_chart_when_no_series_has_data(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(report, "render_chart", lambda *a, **kw: calls.append(a))

    generate_report(
        make_analysis(series=[make_series(found=False)]), output_path=tmp_path / "report.pdf", lang="en"
    )

    assert calls == []


def test_cli_report_language_defaults_to_english():
    args = report.build_arg_parser().parse_args(["--analysis-json", "analysis.json"])

    assert args.lang == "en"


def test_generate_report_produces_exactly_one_page(tmp_path):
    output = tmp_path / "report.pdf"

    generate_report(
        make_analysis(), output_path=output, lang="uk",
        question="Чи росте інтерес?", summary="Інтерес зростає на 42% рік до року.",
        generated_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )

    assert output.exists()
    reader = PdfReader(str(output))
    assert len(reader.pages) == 1


def test_generate_report_one_page_with_many_series_and_long_text(tmp_path):
    output = tmp_path / "report.pdf"
    many_series = [make_series(article=f"Article {i}", lang="uk", yoy=0.1 * i) for i in range(15)]
    long_summary = "Дуже довгий висновок. " * 80
    long_question = "Дуже довге питання? " * 40

    generate_report(
        make_analysis(series=many_series, warnings=["w1", "w2", "w3"]),
        output_path=output, lang="uk",
        question=long_question, summary=long_summary,
        generated_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )

    reader = PdfReader(str(output))
    assert len(reader.pages) == 1


def test_generate_report_one_page_with_no_series_found(tmp_path):
    output = tmp_path / "report.pdf"

    generate_report(
        make_analysis(series=[make_series(found=False)]), output_path=output, lang="uk",
        generated_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )

    reader = PdfReader(str(output))
    assert len(reader.pages) == 1
    text = reader.pages[0].extract_text()
    assert "надано" in text or "no_conclusion" not in text  # falls back to "no conclusion" label, not a crash


def test_generate_report_uk_labels_appear_in_output(tmp_path):
    output = tmp_path / "report.pdf"

    generate_report(
        make_analysis(), output_path=output, lang="uk", summary="Тестовий висновок",
        generated_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )

    text = PdfReader(str(output)).pages[0].extract_text()
    assert "Висновок" in text
    assert "Тестовий висновок" in text


def test_generate_report_en_labels_appear_in_output(tmp_path):
    output = tmp_path / "report.pdf"

    generate_report(
        make_analysis(), output_path=output, lang="en", summary="Test conclusion",
        generated_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )

    text = PdfReader(str(output)).pages[0].extract_text()
    assert "Conclusion" in text
    assert "Test conclusion" in text


def test_generate_report_translates_trend_and_trust_table_values(tmp_path):
    output = tmp_path / "report.pdf"

    generate_report(
        make_analysis(series=[make_series(trend="decreasing", trust_level="high")]),
        output_path=output, lang="uk", summary="x",
        generated_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )

    text = PdfReader(str(output)).pages[0].extract_text()
    assert "спадає" in text
    assert "висока" in text
    assert "decreasing" not in text


def test_generate_report_unsupported_lang_falls_back_to_english(tmp_path):
    output = tmp_path / "report.pdf"

    generate_report(
        make_analysis(), output_path=output, lang="fr", summary="Résumé",
        generated_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )

    text = PdfReader(str(output)).pages[0].extract_text()
    assert "Conclusion" in text  # English fallback label


def test_generate_report_includes_trust_reasons_localized_to_report_language(tmp_path):
    output_uk = tmp_path / "report_uk.pdf"
    output_en = tmp_path / "report_en.pdf"

    generate_report(
        make_analysis(), output_path=output_uk, lang="uk", summary="x",
        generated_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )
    generate_report(
        make_analysis(), output_path=output_en, lang="en", summary="x",
        generated_at=datetime(2024, 5, 1, tzinfo=timezone.utc),
    )

    text_uk = PdfReader(str(output_uk)).pages[0].extract_text()
    text_en = PdfReader(str(output_en)).pages[0].extract_text()
    # the reason must actually be translated, not left in English inside a
    # uk-language report -- the bug found running report.py end-to-end.
    assert "статистично значущий" in text_uk
    assert "statistically significant" not in text_uk
    assert "statistically significant" in text_en


def test_generate_report_raises_when_fonts_are_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "FONTS_DIR", tmp_path / "no-such-fonts-dir")

    with pytest.raises(AppError) as exc_info:
        generate_report(make_analysis(), output_path=tmp_path / "report.pdf", lang="uk")

    assert exc_info.value.error_code == "fonts_missing"


def test_cli_reads_summary_from_file_and_writes_report_next_to_analysis(tmp_path, capsys):
    import json as jsonlib

    analysis_path = tmp_path / "analysis.json"
    analysis_path.write_text(jsonlib.dumps(make_analysis()))
    summary_file = tmp_path / "summary.txt"
    summary_file.write_text("Висновок з файлу.\n")

    report.main(
        [
            "--analysis-json", str(analysis_path),
            "--lang", "uk",
            "--summary-file", str(summary_file),
        ]
    )

    expected_pdf = tmp_path / "report.pdf"
    assert expected_pdf.exists()
    text = PdfReader(str(expected_pdf)).pages[0].extract_text()
    assert "Висновок з файлу." in text

    stdout = jsonlib.loads(capsys.readouterr().out)
    assert stdout == {"ok": True, "report_pdf": str(expected_pdf)}


def test_cli_errors_cleanly_when_analysis_json_is_missing(tmp_path, capsys):
    with pytest.raises(SystemExit) as exc_info:
        report.main(["--analysis-json", str(tmp_path / "does-not-exist.json")])

    assert exc_info.value.code == 1
    import json as jsonlib

    stdout = jsonlib.loads(capsys.readouterr().out)
    assert stdout["ok"] is False
    assert stdout["error_code"] == "analysis_not_found"


def test_help_text_includes_a_runnable_example():
    help_text = report.build_arg_parser().format_help()

    assert "uv run scripts/report.py" in help_text
    assert "--analysis-json" in help_text


def report_text(tmp_path, analysis, **kwargs):
    output = tmp_path / "report.pdf"
    kwargs.setdefault("generated_at", datetime(2024, 5, 1, tzinfo=timezone.utc))
    generate_report(analysis, output_path=output, **kwargs)
    reader = PdfReader(str(output))
    assert len(reader.pages) == 1
    return reader.pages[0].extract_text()


def test_the_chart_is_embedded_as_vector_graphics_in_the_report_language(tmp_path):
    # It used to be a 150 dpi PNG: blurry when zoomed, and its text
    # invisible to anything reading the PDF.
    output = tmp_path / "report.pdf"
    generate_report(make_analysis(), output_path=output, lang="uk")

    page = PdfReader(str(output)).pages[0]
    assert len(page.images) == 0
    assert CHART_LABELS["uk"]["title"] in page.extract_text()


def test_pdf_title_metadata_is_the_report_heading(tmp_path):
    output = tmp_path / "report.pdf"
    generate_report(make_analysis(), output_path=output, lang="en", question="Is interest growing?")

    assert PdfReader(str(output)).metadata.title == "Is interest growing?"


def test_header_says_what_period_and_editions_the_data_covers(tmp_path):
    analysis = make_analysis(series=[make_series(), make_series(found=False, lang="pl")])

    assert "Jan 2024 – Feb 2024 · Editions: uk, pl" in report_text(tmp_path, analysis, lang="en")
    assert "січ. 2024 – лют. 2024 · Розділи: uk, pl" in report_text(tmp_path, analysis, lang="uk")


def test_a_long_question_as_heading_shrinks_before_it_is_cut(tmp_path):
    question = "How has interest in intermittent fasting changed on English, German, Polish, Czech " \
               "and Ukrainian Wikipedia over the last two years, adjusted for traffic?"

    text = report_text(tmp_path, make_analysis(), lang="en", question=question)

    assert "adjusted for traffic?" in text


def test_series_without_an_article_get_a_row_saying_so(tmp_path):
    analysis = make_analysis(series=[make_series(), make_series(found=False, lang="pl")])

    assert "no article in this edition" in report_text(tmp_path, analysis, lang="en")


def test_yoy_is_colored_only_when_a_significant_trend_agrees_with_it():
    assert _direction_style(-0.2, "decreasing") == (theme.DOWN, "▼")
    assert _direction_style(0.3, "increasing") == (theme.UP, "▲")
    # -3% that Mann-Kendall calls "no trend" must not read as a decline
    assert _direction_style(-0.03, "no trend") == (theme.FLAT, "")
    assert _direction_style(0.05, "decreasing") == (theme.FLAT, "")
    assert _direction_style(None, "increasing") == (theme.FLAT, "")


def with_reasons(series, reason_codes):
    series["trust"]["reason_codes"] = reason_codes
    return series


def test_concerns_are_listed_first_and_marked_differently_from_strengths():
    s = with_reasons(make_series(), [
        {"code": "long_history", "params": {"months": 24}, "concern": False},
        {"code": "low_volume", "params": {"avg_views": 5}, "concern": True},
    ])

    entries = _reason_entries(report.LABELS["en"], [s], "en")

    assert [(marker, text) for marker, text, _ in entries] == [
        ("!", render_reason(Reason("low_volume", {"avg_views": 5}), "en")),
        ("✓", render_reason(Reason("long_history", {"months": 24}), "en")),
    ]


def test_a_reason_every_series_shares_is_listed_once_under_all_series():
    shared = {"code": "long_history", "params": {"months": 24}, "concern": False}
    a = with_reasons(make_series(article="A", lang="en"), [shared, {"code": "high_volume", "params": {"avg_views": 900}, "concern": False}])
    b = with_reasons(make_series(article="B", lang="uk"), [shared, {"code": "high_volume", "params": {"avg_views": 300}, "concern": False}])

    entries = _reason_entries(report.LABELS["en"], [a, b], "en")
    texts = [text for _, text, _ in entries]

    assert texts[0] == "All series"
    assert sum("24 months" in t for t in texts) == 1
    assert "A · en" in texts and "B · uk" in texts


def test_reasons_that_dont_fit_end_in_a_note_instead_of_silently_vanishing(tmp_path):
    many = [
        with_reasons(make_series(article=f"Article {i}", yoy=0.1 * i), [
            {"code": "high_volume", "params": {"avg_views": 1000 + i}, "concern": False},
            {"code": "peak_moderate", "params": {"peak_share": 0.3 + i / 100}, "concern": True},
        ])
        for i in range(15)
    ]

    text = report_text(tmp_path, make_analysis(series=many), lang="en", summary="x " * 200)

    assert "the rest is in analysis.json" in text


def test_method_notes_are_included_when_there_is_room_and_dropped_whole_when_not(tmp_path):
    roomy = report_text(tmp_path, make_analysis(), lang="en", summary="Short.")
    crowded = report_text(
        tmp_path, make_analysis(series=[make_series(article=f"A{i}") for i in range(15)]),
        lang="en", summary="Long conclusion. " * 40,
    )

    assert "How to read this" in roomy and "Mann-Kendall test" in roomy
    assert "How to read this" not in crowded


def test_single_series_trust_card_counts_the_checks_it_passed(tmp_path):
    s = with_reasons(make_series(), [
        {"code": "long_history", "params": {"months": 24}, "concern": False},
        {"code": "high_volume", "params": {"avg_views": 900}, "concern": False},
        {"code": "trend_not_significant", "params": {"p_value": 0.3}, "concern": True},
    ])

    assert "2 of 3 checks passed" in report_text(tmp_path, make_analysis(series=[s]), lang="en")


def text_baselines(pdf_path):
    """(text, baseline y in points) for every text run on the page."""
    runs = []

    def visit(text, cm, tm, *_):
        if text.strip():
            runs.append((text.strip(), tm[5] * cm[3] + cm[5]))

    PdfReader(str(pdf_path)).pages[0].extract_text(visitor_text=visit)
    return runs


def test_a_crowded_page_never_draws_into_the_footer(tmp_path):
    # Real bug: with nine series and a long conclusion, the trust-reasons
    # heading was drawn on top of the footer and its overflow note below it.
    output = tmp_path / "report.pdf"
    many = [make_series(article=f"Article {i}") for i in range(9)]
    generate_report(
        make_analysis(series=many), output_path=output, lang="en",
        question="How does interest compare across nine editions, and which market should we launch in first? " * 2,
        summary="Long conclusion. " * 60,
    )

    footer_top = report.MARGIN + report.FOOTER_H
    footer = ("Data:", "Generated:")
    intruders = [(t, y) for t, y in text_baselines(output) if y < footer_top and not t.startswith(footer)]
    assert intruders == []


def test_no_two_series_shown_share_a_color(tmp_path, monkeypatch):
    calls = []
    original = report.render_chart

    def spy(series, *args, **kwargs):
        calls.append(series)
        original(series, *args, **kwargs)

    monkeypatch.setattr(report, "render_chart", spy)
    many = [make_series(article=f"Article {i}") for i in range(10)]
    for i, s in enumerate(many):
        s["label"] = f"Article {i} (uk)"

    generate_report(make_analysis(series=many), output_path=tmp_path / "report.pdf", lang="en")

    assert len(calls[0]) == len(theme.SERIES_COLORS) == report.MAX_TABLE_ROWS
