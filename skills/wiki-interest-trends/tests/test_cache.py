from pathlib import Path

import pytest

from wikitrends.cache import Cache, cache_key, default_cache_path


class FakeClock:
    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def cache(tmp_path, clock):
    return Cache(path=tmp_path, clock=clock)


def test_set_then_get_returns_the_same_value(cache):
    cache.set("k", {"views": 42})

    assert cache.get("k") == {"views": 42}


def test_get_missing_key_returns_none(cache):
    assert cache.get("does-not-exist") is None


def test_entry_without_ttl_never_expires(cache, clock):
    cache.set("k", "permanent", ttl_seconds=None)

    clock.advance(10_000_000)

    assert cache.get("k") == "permanent"


def test_entry_with_ttl_is_available_before_expiry(cache, clock):
    cache.set("k", "short-lived", ttl_seconds=60)

    clock.advance(59)

    assert cache.get("k") == "short-lived"


def test_entry_with_ttl_expires_after_ttl_elapses(cache, clock):
    cache.set("k", "short-lived", ttl_seconds=60)

    clock.advance(61)

    assert cache.get("k") is None


def test_overwriting_a_key_replaces_its_value(cache):
    cache.set("k", "first")
    cache.set("k", "second")

    assert cache.get("k") == "second"


def test_cache_key_is_stable_regardless_of_dict_argument_order():
    key_a = cache_key("pageviews", {"lang": "uk", "article": "X"})
    key_b = cache_key("pageviews", {"article": "X", "lang": "uk"})

    assert key_a == key_b


def test_cache_key_differs_for_different_arguments():
    key_a = cache_key("pageviews", {"lang": "uk"})
    key_b = cache_key("pageviews", {"lang": "pl"})

    assert key_a != key_b


def test_default_cache_path_uses_wikitrends_cache_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKITRENDS_CACHE", str(tmp_path / "custom"))

    assert default_cache_path() == tmp_path / "custom"


def test_default_cache_path_falls_back_to_home_cache_dir(monkeypatch):
    monkeypatch.delenv("WIKITRENDS_CACHE", raising=False)

    assert default_cache_path() == Path.home() / ".cache" / "wikitrends"
