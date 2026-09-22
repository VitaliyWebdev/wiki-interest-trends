from wikitrends.cache import Cache
from wikitrends.errors import AppError
from wikitrends.wikidata import (
    ArticleLookup,
    Candidate,
    get_sitelinks,
    resolve_redirect,
    search_entities,
)

from fakes import FakeResponse, FakeSession, load_fixture


def make_cache(tmp_path):
    return Cache(path=tmp_path)


def test_search_entities_returns_candidates_from_real_fixture(tmp_path):
    fixture = load_fixture("wikidata", "search_intermittent_fasting_uk.json")
    session = FakeSession([FakeResponse(200, fixture)])

    candidates = search_entities(
        session, make_cache(tmp_path), query="інтервальне голодування", language="uk"
    )

    assert candidates == [
        Candidate(
            qid="Q1666254",
            label="intermittent fasting",
            description="a diet that cycles between a period of fasting and non-fasting",
        )
    ]


def test_search_entities_returns_empty_list_when_no_matches(tmp_path):
    fixture = load_fixture("wikidata", "search_no_results.json")
    session = FakeSession([FakeResponse(200, fixture)])

    candidates = search_entities(
        session, make_cache(tmp_path), query="zzzzznonexistentquery12345", language="en"
    )

    assert candidates == []


def test_search_entities_surfaces_all_ambiguous_candidates(tmp_path):
    fixture = load_fixture("wikidata", "search_mercury_uk.json")
    session = FakeSession([FakeResponse(200, fixture)])

    candidates = search_entities(session, make_cache(tmp_path), query="Меркурій", language="uk")

    # Real ambiguous case: planet, chemical element, Roman god, a US city, a
    # ship all share the label "Меркурій" in Wikidata. resolve_topic.py must
    # hand all of them to the agent, not silently pick one.
    assert len(candidates) == 5
    descriptions = {c.description for c in candidates}
    assert "first planet from the Solar System and smallest among all, tellurian and with extreme temperatures" in descriptions
    assert "chemical element with symbol Hg and atomic number 80" in descriptions
    assert "Roman god of trade, merchants, thieves and travel" in descriptions


def test_search_entities_caches_so_second_call_does_not_hit_network(tmp_path):
    fixture = load_fixture("wikidata", "search_intermittent_fasting_uk.json")
    session = FakeSession([FakeResponse(200, fixture)])
    cache = make_cache(tmp_path)

    search_entities(session, cache, query="інтервальне голодування", language="uk")
    search_entities(session, cache, query="інтервальне голодування", language="uk")

    assert len(session.calls) == 1


def test_get_sitelinks_reports_found_and_missing_languages(tmp_path):
    fixture = load_fixture("wikidata", "sitelinks_q1666254_pl_cs_uk.json")
    session = FakeSession([FakeResponse(200, fixture)])

    result = get_sitelinks(session, make_cache(tmp_path), qid="Q1666254", langs=["pl", "cs", "uk"])

    assert result == {
        "pl": ArticleLookup(status="missing"),
        "cs": ArticleLookup(status="found", title="Přerušovaný půst"),
        "uk": ArticleLookup(status="found", title="Інтервальне голодування"),
    }


def test_get_sitelinks_raises_app_error_for_invalid_qid(tmp_path):
    fixture = load_fixture("wikidata", "sitelinks_invalid_qid.json")
    session = FakeSession([FakeResponse(200, fixture)])

    try:
        get_sitelinks(session, make_cache(tmp_path), qid="Q999999999999", langs=["uk"])
        assert False, "expected AppError"
    except AppError as exc:
        assert exc.error_code == "qid_not_found"


def test_resolve_redirect_returns_canonical_title_for_a_redirect(tmp_path):
    fixture = load_fixture("wikidata", "redirect_usa_uk.json")
    session = FakeSession([FakeResponse(200, fixture)])

    resolved = resolve_redirect(session, make_cache(tmp_path), lang="uk", title="США")

    assert resolved == "Сполучені Штати Америки"


def test_resolve_redirect_returns_same_title_when_already_canonical(tmp_path):
    fixture = load_fixture("wikidata", "redirect_none_uk.json")
    session = FakeSession([FakeResponse(200, fixture)])

    resolved = resolve_redirect(
        session, make_cache(tmp_path), lang="uk", title="Інтервальне голодування"
    )

    assert resolved == "Інтервальне голодування"
