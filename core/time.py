"""後方互換シム: 実体は :mod:`shared.kernel.time.clock` へ移動した。

UTC 時刻ヘルパは Shared Kernel の time パッケージに集約する。既存の
``from core.time import utc_now, utc_now_isoformat`` を壊さないよう再公開する。
新規コードは ``shared.kernel.time.clock`` を直接 import すること。
"""

from shared.kernel.time.clock import utc_now, utc_now_isoformat

__all__ = ["utc_now", "utc_now_isoformat"]
