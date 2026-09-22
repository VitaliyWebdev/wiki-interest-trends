import urllib.parse
from dataclasses import dataclass
from datetime import date
from typing import Any, List, Optional

from .cache import Cache, cache_key
from .errors import AppError
from .http import get_json

PAGEVIEWS_API = "https://wikimedia.org/api/rest_v1/metrics/pageviews"

# A closed month/day never changes again -> cache forever. The current,
# still-accumulating period changes every time Wikimedia recomputes it, so
# it only gets a short TTL. See docs/dev/cache.md for why this policy lives
# here and not in cache.py itself.
CURRENT_PERIOD_TTL_SECONDS = 6 * 3600
CLOSED_PERIOD_TTL_SECONDS = None
REDIRECTS_TTL_SECONDS = 7 * 24 * 3600


def encode_article_title(title: str) -> str:
    """Space -> underscore, then percent-encode everything including '/'.
    Confirmed by real request: a literal '/' in the path is read by the
    pageviews API as a route separator, turning a title like "AC/DC" into a
    404 "invalid route" instead of a real answer."""
    return urllib.parse.quote(title.replace(" ", "_"), safe="")


def _ttl_for_end_date(end: str, today: date) -> Optional[int]:
    end_period = end[:6]  # YYYYMMDD -> YYYYMM
    current_period = today.strftime("%Y%m")
    return CURRENT_PERIOD_TTL_SECONDS if end_period >= current_period else CLOSED_PERIOD_TTL_SECONDS


@dataclass
class MonthlyPoint:
    timestamp: str
    views: int


@dataclass
class PerArticleSeries:
    found: bool
    points: List[MonthlyPoint]


@dataclass
class NormalizedPoint:
    timestamp: str
    views: int
    project_total: int
    per_million: float


def fetch_per_article(
    session: Any,
    cache: Cache,
    project: str,
    article: str,
    start: str,
    end: str,
    granularity: str = "monthly",
    *,
    today: Optional[date] = None,
) -> PerArticleSeries:
    today = today or date.today()
    key = cache_key("per-article", project, article, granularity, start, end)
    payload = cache.get(key)

    if payload is None:
        encoded = encode_article_title(article)
        url = (
            f"{PAGEVIEWS_API}/per-article/{project}/all-access/user/"
            f"{encoded}/{granularity}/{start}/{end}"
        )
        result = get_json(session, url)
        if result.status_code == 404:
            if result.data and result.data.get("detail") == "invalid route":
                raise AppError(
                    error_code="internal_request_error",
                    message=f"Malformed pageviews request for article {article!r}",
                    hint="This means our own title encoding is wrong, not that the article has no data.",
                )
            payload = {"found": False, "items": []}
        else:
            payload = {"found": True, "items": result.data.get("items", [])}
        cache.set(key, payload, ttl_seconds=_ttl_for_end_date(end, today))

    return PerArticleSeries(
        found=payload["found"],
        points=[MonthlyPoint(item["timestamp"], item["views"]) for item in payload["items"]],
    )


def fetch_aggregate(
    session: Any,
    cache: Cache,
    project: str,
    start: str,
    end: str,
    granularity: str = "monthly",
    *,
    today: Optional[date] = None,
) -> List[MonthlyPoint]:
    today = today or date.today()
    key = cache_key("aggregate", project, granularity, start, end)
    items = cache.get(key)

    if items is None:
        url = f"{PAGEVIEWS_API}/aggregate/{project}/all-access/user/{granularity}/{start}/{end}"
        result = get_json(session, url)
        items = result.data.get("items", [])
        cache.set(key, items, ttl_seconds=_ttl_for_end_date(end, today))

    return [MonthlyPoint(item["timestamp"], item["views"]) for item in items]


def fetch_redirects_of(session: Any, cache: Cache, lang: str, title: str) -> List[str]:
    key = cache_key("redirects_of", lang, title)
    cached = cache.get(key)
    if cached is not None:
        return cached

    titles: List[str] = []
    rdcontinue: Optional[str] = None
    while True:
        url = (
            f"https://{lang}.wikipedia.org/w/api.php?action=query"
            f"&titles={urllib.parse.quote(title)}&prop=redirects&rdlimit=500&format=json"
        )
        if rdcontinue:
            url += f"&rdcontinue={urllib.parse.quote(rdcontinue)}"
        result = get_json(session, url)
        pages = result.data.get("query", {}).get("pages", {})
        for page in pages.values():
            titles.extend(r["title"] for r in page.get("redirects", []))
        rdcontinue = result.data.get("continue", {}).get("rdcontinue")
        if not rdcontinue:
            break

    cache.set(key, titles, ttl_seconds=REDIRECTS_TTL_SECONDS)
    return titles


def normalize_series(
    article_points: List[MonthlyPoint], aggregate_points: List[MonthlyPoint]
) -> List[NormalizedPoint]:
    totals = {p.timestamp: p.views for p in aggregate_points}
    result = []
    for point in article_points:
        total = totals.get(point.timestamp)
        if not total:
            continue
        result.append(
            NormalizedPoint(
                timestamp=point.timestamp,
                views=point.views,
                project_total=total,
                per_million=(point.views / total) * 1_000_000,
            )
        )
    return result
