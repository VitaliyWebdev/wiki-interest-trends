import urllib.parse
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from .cache import Cache, cache_key
from .errors import AppError
from .http import get_json

WIKIDATA_API = "https://www.wikidata.org/w/api.php"

# Wikidata labels/sitelinks/redirects change rarely; cache aggressively so
# repeat queries about the same topic don't hit the network at all.
CACHE_TTL_SECONDS = 7 * 24 * 3600


@dataclass
class Candidate:
    qid: str
    label: str
    description: str


@dataclass
class ArticleLookup:
    status: str  # "found" | "missing"
    title: Optional[str] = None


def _cached_get(session: Any, cache: Cache, key: str, url: str) -> Any:
    data = cache.get(key)
    if data is not None:
        return data
    result = get_json(session, url)
    cache.set(key, result.data, ttl_seconds=CACHE_TTL_SECONDS)
    return result.data


def search_entities(
    session: Any, cache: Cache, query: str, language: str, limit: int = 5
) -> List[Candidate]:
    key = cache_key("wbsearchentities", query, language, limit)
    url = (
        f"{WIKIDATA_API}?action=wbsearchentities&search={urllib.parse.quote(query)}"
        f"&language={language}&format=json&limit={limit}"
    )
    data = _cached_get(session, cache, key, url)

    return [
        Candidate(
            qid=item["id"],
            label=item.get("label", item["id"]),
            description=item.get("description", ""),
        )
        for item in data.get("search", [])
    ]


def get_sitelinks(
    session: Any, cache: Cache, qid: str, langs: List[str]
) -> Dict[str, ArticleLookup]:
    sitefilter = "|".join(f"{lang}wiki" for lang in langs)
    key = cache_key("wbgetentities_sitelinks", qid, tuple(sorted(langs)))
    url = (
        f"{WIKIDATA_API}?action=wbgetentities&ids={qid}&props=sitelinks"
        f"&sitefilter={urllib.parse.quote(sitefilter, safe='|')}&format=json"
    )
    data = _cached_get(session, cache, key, url)

    if "error" in data:
        raise AppError(
            error_code="qid_not_found",
            message=f"Wikidata has no entity {qid}: {data['error'].get('info', '')}",
            hint="Double check the QID came from resolve_topic.py's candidate list.",
        )

    sitelinks = data.get("entities", {}).get(qid, {}).get("sitelinks", {})
    result: Dict[str, ArticleLookup] = {}
    for lang in langs:
        site_key = f"{lang}wiki"
        if site_key in sitelinks:
            result[lang] = ArticleLookup(status="found", title=sitelinks[site_key]["title"])
        else:
            result[lang] = ArticleLookup(status="missing")
    return result


def resolve_redirect(session: Any, cache: Cache, lang: str, title: str) -> str:
    key = cache_key("resolve_redirect", lang, title)
    url = (
        f"https://{lang}.wikipedia.org/w/api.php?action=query"
        f"&titles={urllib.parse.quote(title)}&redirects&format=json"
    )
    data = _cached_get(session, cache, key, url)

    pages = data.get("query", {}).get("pages", {})
    for page in pages.values():
        if "title" in page:
            return page["title"]
    return title
