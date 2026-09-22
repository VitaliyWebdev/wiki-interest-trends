#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["requests==2.34.2", "matplotlib==3.11.2"]
# ///
"""Pageview trend analysis: raw + normalized views, year-over-year growth,
trend significance (Theil-Sen slope + Mann-Kendall test), a deterministic
trust level with reasons, and a comparison chart -- for one or more topics
across one or more language editions.

Two ways to say what to analyze:
  --qids Q1,Q2 --langs pl,cs,uk   Compare topic(s) (by Wikidata QID, from
                                   resolve_topic.py) across language editions.
                                   Missing-language pairs are reported, not
                                   errors.
  --titles "A,B" --lang uk        Compare specific article titles directly,
                                   within one language edition -- use this
                                   when you already know the exact titles
                                   (e.g. a repeat query) and don't need
                                   Wikidata resolution.

Date range: either --last (e.g. 24m, 90d) or explicit --start/--end
(YYYYMMDD). --last Nm uses the N most recently *completed* calendar months
(not today's partial month) so year-over-year comparisons are always
comparing whole months to whole months.

Examples:
  uv run scripts/analyze.py --qids Q1666254 --langs pl,cs,uk --last 24m
  uv run scripts/analyze.py --titles "Python (programming language),Ruby (programming language)" --lang en --last 24m
  uv run scripts/analyze.py --qids Q1666254 --langs uk --start 20220101 --end 20240630 --include-redirects
"""
import argparse
import calendar
import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, str(Path(__file__).parent))

from wikitrends.cache import Cache
from wikitrends.chart import render_chart
from wikitrends.cli import make_session_and_cache, new_run_dir, run_cli
from wikitrends.errors import AppError
from wikitrends.pageviews import (
    MonthlyPoint,
    PerArticleSeries,
    fetch_aggregate,
    fetch_per_article,
    fetch_redirects_of,
    normalize_series,
)
from wikitrends.stats import (
    average_monthly_views,
    mann_kendall_test,
    peak_share,
    seasonality_ratio,
    theil_sen_log_slope,
    year_over_year_growth,
)
from wikitrends.trust import assess_trust
from wikitrends.wikidata import get_sitelinks

EARLIEST_PER_ARTICLE_DATE = "20150701"


def _last_day_of_month(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def _shift_month(year: int, month: int, delta: int) -> Tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def _parse_last(value: str) -> Tuple[int, str]:
    if len(value) < 2 or value[-1] not in ("m", "d"):
        raise AppError(
            error_code="bad_arguments",
            message=f"Invalid --last value {value!r}",
            hint="Use a number followed by 'm' (months) or 'd' (days), e.g. 24m or 90d.",
        )
    try:
        amount = int(value[:-1])
    except ValueError:
        raise AppError(
            error_code="bad_arguments",
            message=f"Invalid --last value {value!r}",
            hint="Use a number followed by 'm' (months) or 'd' (days), e.g. 24m or 90d.",
        )
    if amount <= 0:
        raise AppError(
            error_code="bad_arguments",
            message=f"--last amount must be positive, got {amount}",
            hint="Use a number followed by 'm' (months) or 'd' (days), e.g. 24m or 90d.",
        )
    return amount, value[-1]


def resolve_date_range(
    *,
    start: Optional[str] = None,
    end: Optional[str] = None,
    last: Optional[str] = None,
    granularity: str = "monthly",
    today: Optional[date] = None,
) -> Tuple[str, str, List[str]]:
    """Returns (start, end, warnings) as YYYYMMDD strings.

    --last Nm always resolves to N *complete* calendar months ending at the
    most recent finished month -- not "N months back from today" with
    today's day-of-month, and not including today's still-accumulating
    month. See docs/dev/pageviews.md for why: with monthly granularity, a
    range ending mid-month returns a partial sum for that month, which
    would silently understate year-over-year growth right after a month
    boundary."""
    today = today or date.today()

    if last is not None:
        if start is not None or end is not None:
            raise AppError(
                error_code="bad_arguments",
                message="--last cannot be combined with --start/--end",
                hint="Use either --last, or both --start and --end, not both.",
            )
        amount, unit = _parse_last(last)
        if unit == "m":
            end_year, end_month = _shift_month(today.year, today.month, -1)
            end_date = _last_day_of_month(end_year, end_month)
            start_year, start_month = _shift_month(end_year, end_month, -(amount - 1))
            start_date = date(start_year, start_month, 1)
        else:
            end_date = today
            start_date = today - timedelta(days=amount - 1)
        start = start_date.strftime("%Y%m%d")
        end = end_date.strftime("%Y%m%d")
    elif start is None or end is None:
        raise AppError(
            error_code="bad_arguments",
            message="Provide either --last or both --start and --end",
            hint="Example: --last 24m, or --start 20220101 --end 20231231.",
        )

    warnings: List[str] = []
    if start < EARLIEST_PER_ARTICLE_DATE:
        warnings.append(
            f"Per-article pageview data starts {EARLIEST_PER_ARTICLE_DATE}; "
            f"clipping requested start date {start} to that."
        )
        start = EARLIEST_PER_ARTICLE_DATE

    return start, end, warnings


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analyze.py",
        description=(
            "Analyze Wikipedia pageview trends: raw + normalized views, "
            "year-over-year growth, trend significance, trust level, and a "
            "comparison chart."
        ),
        epilog=(
            "Examples:\n"
            "  uv run scripts/analyze.py --qids Q1666254 --langs pl,cs,uk --last 24m\n"
            '  uv run scripts/analyze.py --titles "Python (programming language),'
            'Ruby (programming language)" --lang en --last 24m\n'
            "  uv run scripts/analyze.py --qids Q1666254 --langs uk --start 20220101"
            " --end 20240630 --include-redirects\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    topic_group = parser.add_argument_group("what to analyze (pick one)")
    topic_group.add_argument("--qids", help="Comma-separated Wikidata QIDs, e.g. Q1666254,Q117")
    topic_group.add_argument(
        "--langs", help="Comma-separated language codes, required with --qids, e.g. pl,cs,uk"
    )
    topic_group.add_argument(
        "--titles", help='Comma-separated article titles in one language, e.g. "A,B"'
    )
    topic_group.add_argument("--lang", help="Language code for --titles, e.g. en")

    range_group = parser.add_argument_group("date range (pick one)")
    range_group.add_argument("--last", help="e.g. 24m (months) or 90d (days)")
    range_group.add_argument("--start", help="YYYYMMDD")
    range_group.add_argument("--end", help="YYYYMMDD")

    parser.add_argument(
        "--granularity", choices=["monthly", "daily"], default="monthly",
        help="Default: monthly. Year-over-year growth and seasonality are only computed at monthly granularity.",
    )
    parser.add_argument(
        "--include-redirects", action="store_true",
        help="Sum pageviews of redirect titles into each article's totals.",
    )
    return parser


def _project_for_lang(lang: str) -> str:
    return f"{lang}.wikipedia"


def _build_targets(
    session: Any, cache: Cache, *, qids: Optional[List[str]], langs: Optional[List[str]],
    titles: Optional[List[str]], lang: Optional[str],
) -> List[Dict[str, Any]]:
    """A "target" is one (topic, language) pair to analyze. In --qids mode
    this expands each QID x each lang via Wikidata sitelinks, including
    entries for languages the topic has no article in ("missing" -- not an
    error, same philosophy as resolve_topic.py). In --titles mode, the
    caller already knows the exact titles, so no Wikidata lookup happens at
    all."""
    targets = []
    if qids:
        for qid in qids:
            articles = get_sitelinks(session, cache, qid=qid, langs=langs)
            for lang_code, lookup in articles.items():
                if lookup.status == "found":
                    targets.append(
                        {
                            "qid": qid,
                            "lang": lang_code,
                            "article": lookup.title,
                            "label": f"{lookup.title} ({lang_code})",
                        }
                    )
                else:
                    targets.append(
                        {
                            "qid": qid,
                            "lang": lang_code,
                            "article": None,
                            "label": f"{qid} ({lang_code})",
                            "found": False,
                            "reason": "no_article_in_language",
                        }
                    )
    else:
        for title in titles:
            targets.append(
                {"qid": None, "lang": lang, "article": title, "label": f"{title} ({lang})"}
            )
    return targets


def _fetch_series_with_redirects(
    session: Any, cache: Cache, *, project: str, lang: str, article: str,
    start: str, end: str, granularity: str, include_redirects: bool, today: Optional[date],
) -> PerArticleSeries:
    main = fetch_per_article(session, cache, project, article, start, end, granularity, today=today)
    if not main.found or not include_redirects:
        return main

    totals = {p.timestamp: p.views for p in main.points}
    for redirect_title in fetch_redirects_of(session, cache, lang, article):
        redirect_series = fetch_per_article(
            session, cache, project, redirect_title, start, end, granularity, today=today
        )
        for p in redirect_series.points:
            totals[p.timestamp] = totals.get(p.timestamp, 0) + p.views

    combined = [MonthlyPoint(ts, totals[ts]) for ts in sorted(totals)]
    return PerArticleSeries(found=True, points=combined)


def _sign(value: Optional[float]) -> Optional[int]:
    if value is None:
        return None
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _analyze_one_target(
    session: Any, cache: Cache, target: Dict[str, Any], *, start: str, end: str,
    granularity: str, include_redirects: bool, today: Optional[date],
) -> Dict[str, Any]:
    if target.get("found") is False:
        return target  # already known unresolvable (no article in this language)

    project = _project_for_lang(target["lang"])
    series = _fetch_series_with_redirects(
        session, cache, project=project, lang=target["lang"], article=target["article"],
        start=start, end=end, granularity=granularity, include_redirects=include_redirects, today=today,
    )
    if not series.found:
        return {**target, "found": False, "reason": "no_pageview_data"}

    aggregate = fetch_aggregate(session, cache, project, start, end, granularity, today=today)
    normalized = normalize_series(series.points, aggregate)

    raw_views = [p.views for p in series.points]
    normalized_views = [p.per_million for p in normalized]

    theil_sen_raw = theil_sen_log_slope(raw_views)
    theil_sen_normalized = theil_sen_log_slope(normalized_views)
    mk = mann_kendall_test(raw_views)
    peak = peak_share(raw_views)

    is_monthly = granularity == "monthly"
    yoy_raw = year_over_year_growth(raw_views) if is_monthly else None
    yoy_normalized = year_over_year_growth(normalized_views) if is_monthly else None
    seasonality = seasonality_ratio(series.points) if is_monthly else None

    trust = assess_trust(
        months_of_data=len(series.points),
        avg_monthly_views=average_monthly_views(raw_views),
        mk_p_value=mk.p_value,
        raw_slope_sign=_sign(theil_sen_raw),
        normalized_slope_sign=_sign(theil_sen_normalized),
        peak_share_top2=peak,
    )

    return {
        **target,
        "found": True,
        "raw": [{"timestamp": p.timestamp, "views": p.views} for p in series.points],
        "normalized_points": normalized,  # NormalizedPoint objects, for chart.py -- stripped before writing analysis.json
        "normalized": [
            {
                "timestamp": p.timestamp,
                "views": p.views,
                "project_total": p.project_total,
                "per_million": p.per_million,
            }
            for p in normalized
        ],
        "metrics": {
            "months_of_data": len(series.points),
            "avg_monthly_views": average_monthly_views(raw_views),
            "yoy_growth_raw": yoy_raw,
            "yoy_growth_normalized": yoy_normalized,
            "theil_sen_slope_raw": theil_sen_raw,
            "theil_sen_slope_normalized": theil_sen_normalized,
            "mann_kendall": {
                "trend": mk.trend,
                "p_value": mk.p_value,
                "s_statistic": mk.s_statistic,
            },
            "peak_share_top2": peak,
            "seasonality_ratio": seasonality,
        },
        "trust": {
            "level": trust.level,
            # "reasons": rendered English text, for quick reading straight out
            # of the JSON. "reason_codes": code+params, so report.py (or any
            # other consumer) can re-render each reason in the report's own
            # language instead of always English -- see docs/dev/stats-and-trust.md.
            "reasons": [r.render("en") for r in trust.reasons],
            "reason_codes": [{"code": r.code, "params": r.params} for r in trust.reasons],
        },
    }


def analyze(
    session: Any,
    cache: Cache,
    *,
    qids: Optional[List[str]] = None,
    langs: Optional[List[str]] = None,
    titles: Optional[List[str]] = None,
    lang: Optional[str] = None,
    start: str,
    end: str,
    granularity: str = "monthly",
    include_redirects: bool = False,
    run_dir: Path,
    today: Optional[date] = None,
) -> Dict[str, Any]:
    targets = _build_targets(session, cache, qids=qids, langs=langs, titles=titles, lang=lang)

    results = [
        _analyze_one_target(
            session, cache, t, start=start, end=end, granularity=granularity,
            include_redirects=include_redirects, today=today,
        )
        for t in targets
    ]

    chart_series = {
        r["label"]: r["normalized_points"] for r in results if r["found"]
    }
    chart_path = run_dir / "chart.png"
    render_chart(chart_series, chart_path, title="Wikipedia pageview trend")

    results_for_json = [
        {k: v for k, v in r.items() if k != "normalized_points"} for r in results
    ]
    analysis = {
        "ok": True,
        "query": {
            "qids": qids, "langs": langs, "titles": titles, "lang": lang,
            "start": start, "end": end, "granularity": granularity,
            "include_redirects": include_redirects,
        },
        "series": results_for_json,
        "chart_path": str(chart_path),
    }
    analysis_path = run_dir / "analysis.json"
    analysis_path.write_text(json.dumps(analysis, ensure_ascii=False, indent=2))

    summary_series = []
    for r in results:
        entry = {"label": r["label"], "lang": r["lang"], "qid": r["qid"], "found": r["found"]}
        if r["found"]:
            entry["yoy_growth"] = r["metrics"]["yoy_growth_raw"]
            entry["trend"] = r["metrics"]["mann_kendall"]["trend"]
            entry["trust_level"] = r["trust"]["level"]
        summary_series.append(entry)

    return {
        "ok": True,
        "run_dir": str(run_dir),
        "analysis_json": str(analysis_path),
        "chart_png": str(chart_path),
        "date_range": {"start": start, "end": end, "granularity": granularity},
        "series": summary_series,
    }


def main(argv=None) -> None:
    args = build_arg_parser().parse_args(argv)

    if bool(args.qids) == bool(args.titles):
        raise AppError(
            error_code="bad_arguments",
            message="Provide exactly one of --qids or --titles",
            hint="Use --qids with --langs for cross-language comparison, or --titles with --lang for direct titles.",
        )
    if args.qids and not args.langs:
        raise AppError(
            error_code="bad_arguments", message="--qids requires --langs",
            hint="Example: --qids Q1666254 --langs pl,cs,uk",
        )
    if args.titles and not args.lang:
        raise AppError(
            error_code="bad_arguments", message="--titles requires --lang",
            hint='Example: --titles "A,B" --lang en',
        )

    start, end, warnings = resolve_date_range(
        start=args.start, end=args.end, last=args.last, granularity=args.granularity
    )

    session, cache = make_session_and_cache()
    run_dir = new_run_dir()

    def run():
        result = analyze(
            session, cache,
            qids=[q.strip() for q in args.qids.split(",")] if args.qids else None,
            langs=[l.strip() for l in args.langs.split(",")] if args.langs else None,
            titles=[t.strip() for t in args.titles.split(",")] if args.titles else None,
            lang=args.lang,
            start=start, end=end, granularity=args.granularity,
            include_redirects=args.include_redirects, run_dir=run_dir,
        )
        if warnings:
            result["warnings"] = warnings
        return result

    run_cli(run)


if __name__ == "__main__":
    main()
