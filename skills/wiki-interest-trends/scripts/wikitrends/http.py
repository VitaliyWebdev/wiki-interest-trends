import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

import requests

from .errors import AppError

DEFAULT_CONTACT = "no contact set, see WIKITRENDS_CONTACT"


def build_session(contact: Optional[str] = None) -> requests.Session:
    session = requests.Session()
    session.headers["User-Agent"] = (
        f"wiki-interest-trends/0.1 (+{contact or DEFAULT_CONTACT})"
    )
    return session


@dataclass
class HttpResult:
    status_code: int
    data: Any


def _safe_json(response: Any) -> Any:
    try:
        return response.json()
    except ValueError:
        return None


def get_json(
    session: Any,
    url: str,
    *,
    max_retries: int = 5,
    backoff_base: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
) -> HttpResult:
    """GET a JSON endpoint. Retries 429/5xx and network errors with
    exponential backoff. 404 is returned as data (it means "no data" for
    Wikimedia pageviews, not a transport failure), never retried. Any other
    4xx raises immediately."""
    attempt = 0
    while True:
        try:
            response = session.get(url)
        except requests.exceptions.RequestException as exc:
            if attempt >= max_retries:
                raise AppError(
                    error_code="network_error",
                    message=f"Network error requesting {url}: {exc}",
                    hint=(
                        "Do not assume this is a real organizational network "
                        "block and tell the user to contact IT -- verify it "
                        "yourself first. This skill talks to several different "
                        "hosts (www.wikidata.org, wikimedia.org, and a "
                        "*.wikipedia.org host per language), so a failure on "
                        "one doesn't mean the others are blocked too -- always "
                        "test the exact URL that just failed, not a different "
                        "one. Run this exact command in the same shell you're "
                        f"already using: curl -sv '{url}'. If that curl "
                        "succeeds, this was a transient failure in this "
                        "process, not a real block -- just retry the script. "
                        "If you're running inside a sandboxed Bash tool (e.g. "
                        "Claude Code with sandboxing on), also check the Bash "
                        "tool's own result for this command -- separately from "
                        "this script's error -- for a message naming a "
                        "disallowed/blocked host; that means your sandbox "
                        "hasn't approved this specific host yet, and the fix "
                        "is approving/declaring that host, not a real network "
                        "problem. Only if none of that explains it should you "
                        "tell the user this specific host may be genuinely "
                        "blocked, and suggest allowlisting it with their admin."
                    ),
                ) from exc
            sleep(backoff_base * (2**attempt))
            attempt += 1
            continue

        if response.status_code == 200:
            return HttpResult(200, _safe_json(response))

        if response.status_code == 404:
            return HttpResult(404, _safe_json(response))

        if response.status_code == 429 or response.status_code >= 500:
            if attempt >= max_retries:
                raise AppError(
                    error_code="upstream_unavailable",
                    message=(
                        f"{url} returned {response.status_code} after "
                        f"{max_retries} retries"
                    ),
                    hint="Wikimedia may be rate-limiting or degraded; try again later.",
                )
            sleep(backoff_base * (2**attempt))
            attempt += 1
            continue

        raise AppError(
            error_code="http_error",
            message=f"{url} returned unexpected status {response.status_code}",
            hint="Check the request parameters (article title encoding, date range).",
        )
