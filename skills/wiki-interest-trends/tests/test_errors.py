from wikitrends.errors import AppError


def test_app_error_to_json_has_required_contract_fields():
    err = AppError(
        error_code="no_data",
        message="No pageviews for this article",
        hint="Try a shorter date range or a different language",
    )

    assert err.to_json() == {
        "ok": False,
        "error_code": "no_data",
        "message": "No pageviews for this article",
        "hint": "Try a shorter date range or a different language",
    }
