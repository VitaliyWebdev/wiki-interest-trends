import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))

import pytest

from analyze import analyze, build_arg_parser, resolve_date_range
from wikitrends.cache import Cache
from wikitrends.errors import AppError

from fakes import FakeResponse, FakeSession, load_fixture


def test_resolve_date_range_last_months_uses_complete_months_only():
    # today is mid-May 2024 -> May is incomplete, so the most recent
    # COMPLETE month is April 2024. --last 3m should give Feb, Mar, Apr.
    start, end, warnings = resolve_date_range(last="3m", today=date(2024, 5, 15))

    assert start == "20240201"
    assert end == "20240430"
    assert warnings == []


def test_resolve_date_range_last_months_spans_a_year_boundary():
    start, end, warnings = resolve_date_range(last="2m", today=date(2024, 1, 15))

    # most recent complete month is Dec 2023; 2 months back from there is Nov 2023
    assert start == "20231101"
    assert end == "20231231"


def test_resolve_date_range_last_days():
    start, end, warnings = resolve_date_range(
        last="10d", granularity="daily", today=date(2024, 5, 15)
    )

    assert start == "20240506"
    assert end == "20240515"


def test_resolve_date_range_explicit_start_end_passthrough():
    start, end, warnings = resolve_date_range(start="20220101", end="20231231")

    assert start == "20220101"
    assert end == "20231231"
    assert warnings == []


def test_resolve_date_range_rejects_last_combined_with_explicit_range():
    with pytest.raises(AppError) as exc_info:
        resolve_date_range(last="24m", start="20220101")

    assert exc_info.value.error_code == "bad_arguments"


def test_resolve_date_range_requires_either_last_or_both_start_and_end():
    with pytest.raises(AppError) as exc_info:
        resolve_date_range(start="20220101")

    assert exc_info.value.error_code == "bad_arguments"


def test_resolve_date_range_clips_start_before_earliest_available_data():
    start, end, warnings = resolve_date_range(start="19990101", end="20200101")

    assert start == "20150701"
    assert len(warnings) == 1
    assert "20150701" in warnings[0]


def test_resolve_date_range_rejects_invalid_last_unit():
    with pytest.raises(AppError) as exc_info:
        resolve_date_range(last="24x")

    assert exc_info.value.error_code == "bad_arguments"


def test_resolve_date_range_rejects_non_numeric_last():
    with pytest.raises(AppError) as exc_info:
        resolve_date_range(last="xxm")

    assert exc_info.value.error_code == "bad_arguments"


def test_help_text_includes_runnable_examples():
    help_text = build_arg_parser().format_help()

    assert "uv run scripts/analyze.py" in help_text
    assert "--qids" in help_text


def test_analyze_qids_mode_found_article_writes_analysis_and_chart(tmp_path):
    sitelinks = load_fixture("wikidata", "sitelinks_q1666254_pl_cs_uk.json")
    per_article = load_fixture("pageviews", "per_article_found_uk.json")
    aggregate = load_fixture("pageviews", "aggregate_uk.json")
    session = FakeSession(
        [FakeResponse(200, sitelinks), FakeResponse(200, per_article), FakeResponse(200, aggregate)]
    )
    cache = Cache(path=tmp_path / "cache")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = analyze(
        session, cache,
        qids=["Q1666254"], langs=["uk"],
        start="20240101", end="20240430", granularity="monthly",
        run_dir=run_dir,
    )

    assert result["ok"] is True
    assert len(result["series"]) == 1
    entry = result["series"][0]
    assert entry["found"] is True
    assert entry["lang"] == "uk"
    assert entry["trend"] in ("increasing", "decreasing", "no trend")

    analysis = json.loads(Path(result["analysis_json"]).read_text())
    assert analysis["ok"] is True
    assert analysis["series"][0]["found"] is True
    assert analysis["series"][0]["article"] == "Інтервальне голодування"
    assert analysis["series"][0]["metrics"]["months_of_data"] == 4
    # report.py redraws its chart from this, so it's part of the contract.
    assert len(analysis["series"][0]["normalized"]) == 4
    assert set(analysis["series"][0]["normalized"][0]) == {"timestamp", "views", "project_total", "per_million"}
    # ...and so is each reason's concern flag, which the report marks ✓ / !.
    assert all(isinstance(rc["concern"], bool) for rc in analysis["series"][0]["trust"]["reason_codes"])

    assert Path(result["chart_png"]).exists()
    assert Path(result["chart_png"]).read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"


def test_analyze_qids_mode_missing_language_reported_without_pageview_calls(tmp_path):
    sitelinks = load_fixture("wikidata", "sitelinks_q1666254_pl_cs_uk.json")
    session = FakeSession([FakeResponse(200, sitelinks)])
    cache = Cache(path=tmp_path / "cache")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = analyze(
        session, cache,
        qids=["Q1666254"], langs=["pl"],  # no plwiki sitelink in the fixture
        start="20240101", end="20240430", granularity="monthly",
        run_dir=run_dir,
    )

    assert result["series"] == [
        {"label": "Q1666254 (pl)", "lang": "pl", "qid": "Q1666254", "found": False}
    ]
    assert len(session.calls) == 1  # only the sitelinks lookup, no pageviews call for a missing article

    analysis = json.loads(Path(result["analysis_json"]).read_text())
    assert analysis["series"][0]["reason"] == "no_article_in_language"


def test_analyze_titles_mode_skips_wikidata_entirely(tmp_path):
    per_article = load_fixture("pageviews", "per_article_found_uk.json")
    aggregate = load_fixture("pageviews", "aggregate_uk.json")
    session = FakeSession([FakeResponse(200, per_article), FakeResponse(200, aggregate)])
    cache = Cache(path=tmp_path / "cache")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = analyze(
        session, cache,
        titles=["Інтервальне голодування"], lang="uk",
        start="20240101", end="20240430", granularity="monthly",
        run_dir=run_dir,
    )

    assert result["series"][0]["found"] is True
    assert len(session.calls) == 2  # per-article + aggregate, no Wikidata call at all


def test_analyze_two_different_qids_same_lang_shares_one_aggregate_call(tmp_path):
    sitelinks_fasting = load_fixture("wikidata", "sitelinks_q1666254_pl_cs_uk.json")
    per_article_fasting = load_fixture("pageviews", "per_article_found_uk.json")
    sitelinks_mercury = load_fixture("wikidata", "sitelinks_q308_uk.json")
    per_article_mercury = load_fixture("pageviews", "per_article_found_uk_q308.json")
    aggregate = load_fixture("pageviews", "aggregate_uk.json")
    # Two genuinely different QIDs, each needs its own sitelinks lookup +
    # per-article fetch, but the uk.wikipedia aggregate for the same date
    # range is identical for both and should only be fetched once thanks
    # to the cache. Call order: all sitelinks lookups happen first (the
    # target list is built up front), then per-article/aggregate per target.
    session = FakeSession(
        [
            FakeResponse(200, sitelinks_fasting),
            FakeResponse(200, sitelinks_mercury),
            FakeResponse(200, per_article_fasting),
            FakeResponse(200, aggregate),
            FakeResponse(200, per_article_mercury),
        ]
    )
    cache = Cache(path=tmp_path / "cache")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = analyze(
        session, cache,
        qids=["Q1666254", "Q308"], langs=["uk"],
        start="20240101", end="20240430", granularity="monthly",
        run_dir=run_dir,
    )

    assert len(result["series"]) == 2
    assert len(session.calls) == 5  # not 6 -- the second aggregate call hit the cache


def test_analyze_include_redirects_sums_redirect_views_into_the_main_series(tmp_path):
    main_article = {
        "items": [
            {"timestamp": "20240101" + "00", "views": 100},
            {"timestamp": "20240201" + "00", "views": 120},
        ]
    }
    redirects_of = {
        "query": {
            "pages": {
                "1": {
                    "pageid": 1,
                    "ns": 0,
                    "title": "Main Article",
                    "redirects": [{"pageid": 2, "ns": 0, "title": "Main Article Redirect"}],
                }
            }
        }
    }
    redirect_article = {
        "items": [
            {"timestamp": "20240101" + "00", "views": 5},
            {"timestamp": "20240201" + "00", "views": 7},
        ]
    }
    aggregate = load_fixture("pageviews", "aggregate_uk.json")

    session = FakeSession(
        [
            FakeResponse(200, main_article),
            FakeResponse(200, redirects_of),
            FakeResponse(200, redirect_article),
            FakeResponse(200, aggregate),
        ]
    )
    cache = Cache(path=tmp_path / "cache")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    result = analyze(
        session, cache,
        titles=["Main Article"], lang="uk",
        start="20240101", end="20240430", granularity="monthly",
        include_redirects=True, run_dir=run_dir,
    )

    analysis = json.loads(Path(result["analysis_json"]).read_text())
    raw = analysis["series"][0]["raw"]
    assert raw == [
        {"timestamp": "20240101" + "00", "views": 105},  # 100 + 5
        {"timestamp": "20240201" + "00", "views": 127},  # 120 + 7
    ]


def test_analyze_without_include_redirects_does_not_call_redirects_endpoint(tmp_path):
    main_article = {"items": [{"timestamp": "20240101" + "00", "views": 100}]}
    aggregate = load_fixture("pageviews", "aggregate_uk.json")
    session = FakeSession([FakeResponse(200, main_article), FakeResponse(200, aggregate)])
    cache = Cache(path=tmp_path / "cache")
    run_dir = tmp_path / "run"
    run_dir.mkdir()

    analyze(
        session, cache,
        titles=["Main Article"], lang="uk",
        start="20240101", end="20240430", granularity="monthly",
        include_redirects=False, run_dir=run_dir,
    )

    assert len(session.calls) == 2  # per-article + aggregate only, no redirects lookup
