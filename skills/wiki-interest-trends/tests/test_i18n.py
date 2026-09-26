import report
from wikitrends.chart import CHART_LABELS
from wikitrends import i18n
from wikitrends.i18n import DEFAULT_LANG, SUPPORTED_LANGS, format_compact, format_int, format_pct, month_label, pick
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
        "i18n.MONTHS_SHORT": i18n.MONTHS_SHORT,
        "i18n.THOUSANDS_SEP": i18n.THOUSANDS_SEP,
        "i18n.DECIMAL_SEP": i18n.DECIMAL_SEP,
        "i18n.THOUSAND_SUFFIX": i18n.THOUSAND_SUFFIX,
        "i18n.MILLION_SUFFIX": i18n.MILLION_SUFFIX,
        **{f"trust.REASON_TEMPLATES[{code}]": t for code, t in REASON_TEMPLATES.items()},
    }
    for name, table in tables.items():
        assert set(table) == set(SUPPORTED_LANGS), f"{name} languages: {sorted(table)}"
        reference = _key_shape(table[DEFAULT_LANG])
        for lang in SUPPORTED_LANGS:
            assert _key_shape(table[lang]) == reference, f"{name}[{lang}] keys differ from {DEFAULT_LANG}"


def test_month_label_uses_its_own_names_not_the_process_locale():
    assert month_label(1, 2025, "en") == "Jan 2025"
    assert month_label(9, 2024, "uk") == "вер. 2024"
    assert month_label(5, None, "uk") == "трав."


def test_numbers_use_each_languages_own_separators():
    assert format_int(27880, "en") == "27,880"
    assert format_int(27880, "uk") == "27\u00a0880"  # no-break space: never split across lines
    assert format_compact(27880, "en") == "27.9K"
    assert format_compact(27880, "uk") == "27,9\u00a0тис."
    assert format_compact(972, "uk") == "972"


def test_compact_numbers_keep_a_decimal_only_while_it_adds_a_digit():
    # A live report showed "329,0 тис." -- the ",0" says nothing.
    assert format_compact(328950, "uk") == "329\u00a0тис."
    assert format_compact(328950, "en") == "329K"
    assert format_compact(14000, "en") == "14K"
    assert format_compact(1_260_000, "en") == "1.3M"
    assert format_compact(1_260_000, "uk") == "1,3\u00a0млн"
    assert format_compact(999_700, "en") == "1M"  # not "1000K"
    assert format_compact(960_000, "en") == "960K"


def test_percentages_use_a_real_minus_sign_and_a_dash_for_missing():
    assert format_pct(0.42) == "+42%"
    assert format_pct(-0.2) == "\u221220%"
    assert format_pct(None) == "\u2014"


def test_polish_and_czech_dates_and_numbers():
    assert month_label(10, 2024, "pl") == "paź 2024"
    assert month_label(6, 2024, "cs") == "čvn 2024"
    assert format_int(27880, "pl") == "27 880"
    assert format_compact(27880, "pl") == "27,9 tys."
    assert format_compact(1_260_000, "pl") == "1,3 mln"
    assert format_compact(27880, "cs") == "27,9 tis."
    assert format_compact(1_260_000, "cs") == "1,3 mil."
