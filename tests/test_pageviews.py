from datetime import date

import pytest

from wikitrends.cache import Cache
from wikitrends.errors import AppError
from wikitrends.pageviews import (
    MonthlyPoint,
    encode_article_title,
    fetch_aggregate,
    fetch_per_article,
    fetch_redirects_of,
    normalize_series,
    _ttl_for_end_date,
)

from fakes import FakeResponse, FakeSession, load_fixture


def make_cache(tmp_path):
    return Cache(path=tmp_path)


def test_encode_article_title_replaces_spaces_with_underscores_then_encodes():
    assert encode_article_title("Інтервальне голодування") == (
        "%D0%86%D0%BD%D1%82%D0%B5%D1%80%D0%B2%D0%B0%D0%BB%D1%8C%D0%BD%D0%B5_"
        "%D0%B3%D0%BE%D0%BB%D0%BE%D0%B4%D1%83%D0%B2%D0%B0%D0%BD%D0%BD%D1%8F"
    )


def test_encode_article_title_encodes_slash():
    # Real gotcha found in Stage 0/3 research: default urllib.parse.quote()
    # leaves "/" unescaped, which the pageviews API reads as a path
    # separator and answers with a 404 "invalid route" instead of data.
    assert encode_article_title("AC/DC") == "AC%2FDC"


def test_ttl_for_end_date_is_short_for_the_current_month():
    today = date(2024, 4, 15)
    assert _ttl_for_end_date("20240401", today) == 6 * 3600


def test_ttl_for_end_date_is_forever_for_a_closed_month():
    today = date(2024, 5, 1)
    assert _ttl_for_end_date("20240401", today) is None


def test_fetch_per_article_returns_points_for_a_real_article(tmp_path):
    fixture = load_fixture("pageviews", "per_article_found_uk.json")
    session = FakeSession([FakeResponse(200, fixture)])

    series = fetch_per_article(
        session,
        make_cache(tmp_path),
        project="uk.wikipedia",
        article="Інтервальне голодування",
        start="20240101",
        end="20240430",
        today=date(2024, 5, 1),
    )

    assert series.found is True
    assert series.points == [
        MonthlyPoint("2024010100", 223),
        MonthlyPoint("2024020100", 285),
        MonthlyPoint("2024030100", 313),
        MonthlyPoint("2024040100", 767),
    ]


def test_fetch_per_article_returns_not_found_for_a_real_404(tmp_path):
    fixture = load_fixture("pageviews", "per_article_not_found.json")
    session = FakeSession([FakeResponse(404, fixture)])

    series = fetch_per_article(
        session,
        make_cache(tmp_path),
        project="en.wikipedia",
        article="ThisArticleDoesNotExist12345",
        start="20240101",
        end="20240401",
        today=date(2024, 5, 1),
    )

    assert series.found is False
    assert series.points == []


def test_fetch_per_article_raises_on_our_own_bad_encoding(tmp_path):
    # Real "invalid route" 404 body, captured by deliberately mis-encoding
    # a title containing "/". This must never be reported as "no data" --
    # it means our own URL-building is broken.
    fixture = load_fixture("pageviews", "per_article_invalid_route.json")
    session = FakeSession([FakeResponse(404, fixture)])

    with pytest.raises(AppError) as exc_info:
        fetch_per_article(
            session,
            make_cache(tmp_path),
            project="en.wikipedia",
            article="AC/DC",
            start="20240101",
            end="20240201",
            today=date(2024, 5, 1),
        )

    assert exc_info.value.error_code == "internal_request_error"


def test_fetch_per_article_caches_so_second_call_does_not_hit_network(tmp_path):
    fixture = load_fixture("pageviews", "per_article_found_uk.json")
    session = FakeSession([FakeResponse(200, fixture)])
    cache = make_cache(tmp_path)
    kwargs = dict(
        project="uk.wikipedia",
        article="Інтервальне голодування",
        start="20240101",
        end="20240430",
        today=date(2024, 5, 1),
    )

    fetch_per_article(session, cache, **kwargs)
    fetch_per_article(session, cache, **kwargs)

    assert len(session.calls) == 1


def test_fetch_aggregate_returns_points_from_real_fixture(tmp_path):
    fixture = load_fixture("pageviews", "aggregate_uk.json")
    session = FakeSession([FakeResponse(200, fixture)])

    points = fetch_aggregate(
        session,
        make_cache(tmp_path),
        project="uk.wikipedia",
        start="20240101",
        end="20240430",
        today=date(2024, 5, 1),
    )

    assert points == [
        MonthlyPoint("2024010100", 115282138),
        MonthlyPoint("2024020100", 105744860),
        MonthlyPoint("2024030100", 102268020),
        MonthlyPoint("2024040100", 96763982),
    ]


def test_fetch_redirects_of_paginates_across_multiple_pages(tmp_path):
    page1 = load_fixture("pageviews", "redirects_of_usa_page1.json")
    page2 = load_fixture("pageviews", "redirects_of_usa_page2.json")
    session = FakeSession([FakeResponse(200, page1), FakeResponse(200, page2)])

    titles = fetch_redirects_of(
        session, make_cache(tmp_path), lang="uk", title="Сполучені Штати Америки"
    )

    assert len(session.calls) == 2
    assert len(titles) == 20 + 3  # page1 has 20 redirects, page2 (continuation) has 3
    assert "США" in titles
    assert "USA" in titles
    assert "Америка (держава)" in titles  # from the second page


def test_fetch_redirects_of_caches_so_second_call_does_not_hit_network(tmp_path):
    page1 = load_fixture("pageviews", "redirects_of_usa_page1.json")
    page2 = load_fixture("pageviews", "redirects_of_usa_page2.json")
    session = FakeSession([FakeResponse(200, page1), FakeResponse(200, page2)])
    cache = make_cache(tmp_path)

    fetch_redirects_of(session, cache, lang="uk", title="Сполучені Штати Америки")
    fetch_redirects_of(session, cache, lang="uk", title="Сполучені Штати Америки")

    assert len(session.calls) == 2  # only the first call paginated over the network


def test_normalize_series_computes_per_million_matched_by_timestamp():
    article = [MonthlyPoint("2024010100", 223), MonthlyPoint("2024020100", 285)]
    aggregate = [MonthlyPoint("2024010100", 115282138), MonthlyPoint("2024020100", 105744860)]

    normalized = normalize_series(article, aggregate)

    assert len(normalized) == 2
    assert normalized[0].timestamp == "2024010100"
    assert normalized[0].views == 223
    assert normalized[0].project_total == 115282138
    assert normalized[0].per_million == pytest.approx(223 / 115282138 * 1_000_000)


def test_normalize_series_skips_timestamps_missing_from_aggregate():
    article = [MonthlyPoint("2024010100", 223), MonthlyPoint("2024050100", 400)]
    aggregate = [MonthlyPoint("2024010100", 115282138)]

    normalized = normalize_series(article, aggregate)

    assert len(normalized) == 1
    assert normalized[0].timestamp == "2024010100"
