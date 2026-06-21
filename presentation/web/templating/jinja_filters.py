"""テンプレート向けの Jinja フィルタ.

``create_app()`` 内に定義されていた表示整形フィルタを切り出す。タイムゾーン適用や
JavaScript エスケープといった純粋な整形ロジックを公開関数として実装し、Flask の
リクエストコンテキスト（``g``）への依存は登録ラッパー側に閉じ込める。これにより
整形ロジックをコンテキストなしで単体テストできる。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, tzinfo as TzInfo

from flask import Flask, g

from .timezone import convert_to_timezone


def format_localtime(value, tzinfo: TzInfo, fmt: str | None = "%Y/%m/%d %H:%M"):
    """*value* を指定タイムゾーンで整形する（``datetime`` 以外はそのまま返す）。"""

    if value is None:
        return ""
    if not isinstance(value, datetime):
        return value

    localized = convert_to_timezone(value, tzinfo)
    if localized is None:
        return ""
    if fmt is None:
        return localized
    return localized.strftime(fmt)


def escapejs(value) -> str:
    """JavaScript 文字列リテラルへ安全に埋め込めるようエスケープする。"""

    if value is None:
        return ""

    if not isinstance(value, str):
        value = str(value)

    # ``json.dumps`` がクォートや改行など、文字列リテラルを破壊し得る文字を
    # 適切にエスケープする。テンプレート側が外側のクォートを付与するため、
    # ``json.dumps`` が付ける前後のクォートは取り除く。
    return json.dumps(value, ensure_ascii=False)[1:-1]


def register_template_filters(app: Flask) -> None:
    """アプリへ ``localtime`` / ``escapejs`` フィルタを登録する。"""

    @app.template_filter("localtime")
    def _localtime_filter(value, fmt="%Y/%m/%d %H:%M"):
        """Render *value* in the user's preferred time zone."""

        tzinfo = getattr(g, "user_timezone", timezone.utc)
        return format_localtime(value, tzinfo, fmt)

    @app.template_filter("escapejs")
    def _escapejs_filter(value):
        """Escape a string for safe embedding inside JavaScript strings."""

        return escapejs(value)
