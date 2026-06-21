"""`presentation/web/middleware/unauthorized_handler.py` の純粋ロジックの単体テスト。

未認証理由の分類はログ診断とクライアント挙動（再ログイン誘導）に直結するため、
セッション状態の各組み合わせに対する分類を網羅的に検証する。ハンドラ全体は
既存の統合テスト（auth.unauthorized ログ / X-Session-Expired 応答）で網羅。
"""

from presentation.web.middleware.unauthorized_handler import classify_login_state


def _session_info(**overrides):
    base = {
        "cookie_present": True,
        "user_id_present": True,
        "fresh_login": True,
    }
    base.update(overrides)
    return base


class TestClassifyLoginState:
    def test_cookie_missing_takes_priority(self):
        info = _session_info(cookie_present=False, user_id_present=False)
        assert classify_login_state(info) == "session_cookie_missing"

    def test_cookie_present_without_user_id(self):
        info = _session_info(user_id_present=False)
        assert classify_login_state(info) == "session_cookie_without_user_id"

    def test_session_not_fresh(self):
        info = _session_info(fresh_login=False)
        assert classify_login_state(info) == "session_not_fresh"

    def test_unknown_when_all_present_and_fresh(self):
        assert classify_login_state(_session_info()) == "unknown"

    def test_fresh_none_is_not_treated_as_not_fresh(self):
        # ``fresh_login`` が None（不明）のときは not-fresh と断定しない。
        assert classify_login_state(_session_info(fresh_login=None)) == "unknown"
