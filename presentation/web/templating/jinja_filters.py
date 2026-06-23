"""Jinja2 テンプレート向け純粋整形ユーティリティ。

Flask アプリケーションコンテキストに依存しない純粋関数として実装する。
フィルタ登録は :mod:`presentation.web` の `create_app` で行う。
"""

from __future__ import annotations

from datetime import datetime, timezone as _timezone
from typing import Any


def format_localtime(
    value: Any,
    tz: _timezone,
    fmt: str | None = "%Y/%m/%d %H:%M",
) -> Any:
    """datetime を指定タイムゾーンへ変換してフォーマットする。

    - value が None のとき "" を返す。
    - value が datetime でないとき value をそのまま返す。
    - fmt が None のとき変換後の datetime オブジェクトを返す。
    """
    if value is None:
        return ""
    if not isinstance(value, datetime):
        return value
    converted = value.astimezone(tz)
    if fmt is None:
        return converted
    return converted.strftime(fmt)


def escapejs(value: Any) -> str:
    """JavaScript 文字列リテラル埋め込み用エスケープ。

    - value が None のとき "" を返す。
    - 文字列に強制変換したうえで " → \\" 、改行 → \\n に置換する。
    """
    if value is None:
        return ""
    s = str(value)
    s = s.replace('"', '\\"')
    s = s.replace("\n", "\\n")
    return s
