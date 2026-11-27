from app.shared.utils.diff import diff, redact


def test_nested_credentials_are_redacted() -> None:
    value = {"items": [{"Refresh_Token": "private", "name": "visible"}]}
    assert redact(value) == {"items": [{"Refresh_Token": "***", "name": "visible"}]}
    assert diff({}, value)["items"]["to"] == redact(value)["items"]
