import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest
from pypdf import PdfReader

import report
from report import generate_report
from wikitrends.errors import AppError


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
            "reason_codes": [{"code": "trend_significant", "params": {"p_value": 0.01}}],
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
