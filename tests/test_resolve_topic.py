import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "skills" / "wiki-interest-trends" / "scripts"))

from resolve_topic import build_arg_parser, resolve_topic
from wikitrends.cache import Cache

from fakes import FakeResponse, FakeSession, load_fixture


def test_resolve_topic_assembles_candidates_with_per_language_articles(tmp_path):
    search_fixture = load_fixture("wikidata", "search_intermittent_fasting_uk.json")
    sitelinks_fixture = load_fixture("wikidata", "sitelinks_q1666254_pl_cs_uk.json")
    session = FakeSession([FakeResponse(200, search_fixture), FakeResponse(200, sitelinks_fixture)])
    cache = Cache(path=tmp_path)

    result = resolve_topic(
        session, cache, query="інтервальне голодування", query_lang="uk", langs=["pl", "cs"]
    )

    assert result == {
        "ok": True,
        "candidates": [
            {
                "qid": "Q1666254",
                "label": "intermittent fasting",
                "description": "a diet that cycles between a period of fasting and non-fasting",
                "articles": {
                    "pl": {"status": "missing"},
                    "cs": {"status": "found", "title": "Přerušovaný půst"},
                },
            }
        ],
    }


def test_resolve_topic_returns_empty_candidates_without_extra_lookups(tmp_path):
    search_fixture = load_fixture("wikidata", "search_no_results.json")
    session = FakeSession([FakeResponse(200, search_fixture)])
    cache = Cache(path=tmp_path)

    result = resolve_topic(
        session, cache, query="zzzzznonexistentquery12345", query_lang="en", langs=["uk"]
    )

    assert result == {"ok": True, "candidates": []}
    assert len(session.calls) == 1  # no sitelinks lookup when there are no candidates


def test_help_text_includes_a_runnable_example():
    help_text = build_arg_parser().format_help()

    assert "uv run scripts/resolve_topic.py" in help_text
    assert "--query" in help_text
