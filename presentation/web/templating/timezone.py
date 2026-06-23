"""後方互換シム: 実体は :mod:`shared.kernel.time.timezone` へ移動した。

タイムゾーン解決・変換ユーティリティは Shared Kernel に集約する。既存の
``from presentation.web.templating.timezone import ...`` を壊さないよう
同一オブジェクトを再公開する。新規コードは ``shared.kernel.time.timezone``
を直接 import すること。
"""

from shared.kernel.time.timezone import (
    convert_to_timezone,
    ensure_utc,
    resolve_timezone,
    utc,
)

__all__ = [
    "resolve_timezone",
    "ensure_utc",
    "convert_to_timezone",
    "utc",
]
