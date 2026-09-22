"""Shared test doubles for wikitrends.http.get_json callers.

Kept separate from any one test module because resolve_topic.py, analyze.py
and report.py all end up calling the same http.get_json() underneath, so
every test module that exercises them needs the same fake transport.
"""

import json
from pathlib import Path

FIXTURES_DIR = Path(__file__).parent / "fixtures"


def load_fixture(*parts: str) -> dict:
    path = FIXTURES_DIR.joinpath(*parts)
    return json.loads(path.read_text())


class FakeResponse:
    def __init__(self, status_code, json_data=None, json_raises=False):
        self.status_code = status_code
        self._json_data = json_data
        self._json_raises = json_raises

    def json(self):
        if self._json_raises:
            raise ValueError("response body is not valid JSON")
        return self._json_data


class FakeSession:
    """Queues canned responses/exceptions, one per call to .get()."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url):
        self.calls.append(url)
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item
