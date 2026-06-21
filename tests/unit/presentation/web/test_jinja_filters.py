"""`presentation/web/templating/jinja_filters.py` の純粋整形関数の単体テスト。

タイムゾーン適用と JavaScript エスケープは表示の正しさ・XSS 安全性に関わるため、
Flask コンテキストに依存しない純粋関数として境界条件まで検証する
（フィルタ登録自体は既存のテンプレートテストで網羅）。
"""

from datetime import datetime, timezone, timedelta

from presentation.web.templating.jinja_filters import escapejs, format_localtime


class TestFormatLocaltime:
    def test_none_becomes_empty_string(self):
        assert format_localtime(None, timezone.utc) == ""

    def test_non_datetime_passthrough(self):
        assert format_localtime("not-a-date", timezone.utc) == "not-a-date"
        assert format_localtime(123, timezone.utc) == 123

    def test_formats_in_utc(self):
        dt = datetime(2024, 1, 2, 3, 4, tzinfo=timezone.utc)
        assert format_localtime(dt, timezone.utc) == "2024/01/02 03:04"

    def test_converts_to_target_timezone(self):
        dt = datetime(2024, 1, 2, 3, 4, tzinfo=timezone.utc)
        jst = timezone(timedelta(hours=9))
        assert format_localtime(dt, jst) == "2024/01/02 12:04"

    def test_custom_format(self):
        dt = datetime(2024, 1, 2, 3, 4, tzinfo=timezone.utc)
        assert format_localtime(dt, timezone.utc, "%Y-%m-%d") == "2024-01-02"

    def test_none_format_returns_datetime(self):
        dt = datetime(2024, 1, 2, 3, 4, tzinfo=timezone.utc)
        result = format_localtime(dt, timezone.utc, None)
        assert isinstance(result, datetime)


class TestEscapejs:
    def test_none_becomes_empty_string(self):
        assert escapejs(None) == ""

    def test_escapes_quotes_and_newlines(self):
        result = escapejs('he"llo\n')
        assert '"' not in result.replace('\\"', "")
        assert result == 'he\\"llo\\n'

    def test_non_string_is_coerced(self):
        assert escapejs(42) == "42"

    def test_no_surrounding_quotes(self):
        result = escapejs("plain")
        assert result == "plain"

    def test_unicode_preserved(self):
        assert escapejs("こんにちは") == "こんにちは"
