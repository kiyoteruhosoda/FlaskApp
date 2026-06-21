"""後方互換シム: 実体は :mod:`presentation.web.error_handlers` へ移動した。

旧 ``webapp`` 配下の HTTP エラーハンドラは presentation 層へ統合済み。重複した
実装を残すと挙動が分岐するため、本モジュールは新しい実装をそのまま再公開する。
"""

from presentation.web.error_handlers import *  # noqa: F401,F403
from presentation.web.error_handlers import register_error_handlers  # noqa: F401
