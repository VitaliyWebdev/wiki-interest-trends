import report
from wikitrends.chart import CHART_LABELS
from wikitrends.i18n import DEFAULT_LANG, SUPPORTED_LANGS, pick
from wikitrends.trust import REASON_TEMPLATES


def _key_shape(value):
    if isinstance(value, dict):
        return {k: _key_shape(v) for k, v in value.items()}
    if isinstance(value, list):
        return len(value)
    return None


def test_pick_returns_the_requested_language():
    assert pick({"en": "Trust", "uk": "Довіра"}, "uk") == "Довіра"


def test_pick_falls_back_to_the_default_language_for_unsupported_ones():
    assert DEFAULT_LANG == "en"
    assert pick({"en": "Trust", "uk": "Довіра"}, "fr") == "Trust"


def test_every_user_facing_string_table_covers_every_supported_language():
    # A missing translation doesn't crash anything -- pick() quietly falls
    # back to English -- so the only way to notice a half-translated
    # report is a test that demands identical keys in every language.
    tables = {
        "report.LABELS": report.LABELS,
        "chart.CHART_LABELS": CHART_LABELS,
        **{f"trust.REASON_TEMPLATES[{code}]": t for code, t in REASON_TEMPLATES.items()},
    }
    for name, table in tables.items():
        assert set(table) == set(SUPPORTED_LANGS), f"{name} languages: {sorted(table)}"
        reference = _key_shape(table[DEFAULT_LANG])
        for lang in SUPPORTED_LANGS:
            assert _key_shape(table[lang]) == reference, f"{name}[{lang}] keys differ from {DEFAULT_LANG}"
