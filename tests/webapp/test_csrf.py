from flask import session

from webapp.security import get_or_set_csrf_token, validate_csrf_token


def test_get_or_set_csrf_token_generates_and_reuses_value(app_context):
    app = app_context

    with app.test_request_context():
        assert "_csrf_token" not in session

        token = get_or_set_csrf_token()
        assert isinstance(token, str)
        assert len(token) >= 32
        assert session["_csrf_token"] == token

        second_token = get_or_set_csrf_token()
        assert second_token == token


def test_validate_csrf_token(app_context):
    app = app_context

    with app.test_request_context():
        token = get_or_set_csrf_token()

        assert validate_csrf_token(token) is True
        assert validate_csrf_token("invalid") is False
        assert validate_csrf_token(None) is False

        session.pop("_csrf_token", None)
        assert validate_csrf_token(token) is False
