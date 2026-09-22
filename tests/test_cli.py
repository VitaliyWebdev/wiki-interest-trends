import json

import pytest

from wikitrends.errors import AppError
from wikitrends.cli import make_session_and_cache, new_run_dir, run_cli


def test_run_cli_prints_return_value_as_compact_json(capsys):
    run_cli(lambda: {"ok": True, "value": 42})

    captured = capsys.readouterr()
    assert json.loads(captured.out) == {"ok": True, "value": 42}


def test_run_cli_prints_single_line_json(capsys):
    run_cli(lambda: {"ok": True, "value": 42})

    captured = capsys.readouterr()
    assert captured.out.count("\n") == 1


def test_run_cli_prints_error_contract_and_exits_1_on_app_error(capsys):
    def failing():
        raise AppError(error_code="no_data", message="nothing found", hint="try again")

    with pytest.raises(SystemExit) as exc_info:
        run_cli(failing)

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert json.loads(captured.out) == {
        "ok": False,
        "error_code": "no_data",
        "message": "nothing found",
        "hint": "try again",
    }


def test_make_session_and_cache_uses_wikitrends_contact_env_var(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKITRENDS_CONTACT", "me@example.org")
    monkeypatch.setenv("WIKITRENDS_CACHE", str(tmp_path))

    session, cache = make_session_and_cache()

    assert "me@example.org" in session.headers["User-Agent"]
    cache.set("k", "v")
    assert cache.get("k") == "v"


def test_new_run_dir_creates_a_unique_directory_under_base(tmp_path):
    base = tmp_path / "wikitrends-out"

    run_dir = new_run_dir(base=base)

    assert run_dir.exists()
    assert run_dir.is_dir()
    assert run_dir.parent == base


def test_new_run_dir_calls_never_collide(tmp_path):
    base = tmp_path / "wikitrends-out"

    first = new_run_dir(base=base)
    second = new_run_dir(base=base)

    assert first != second
    assert first.exists()
    assert second.exists()
