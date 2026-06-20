"""後方互換リダイレクト: ``presentation.web.api.version`` への委譲.

DDD 移行で残った重複モジュール。直接 import すると同一 Blueprint へ
ルートを二重登録してアプリ/テストの状態を壊すため、唯一の実体である
presentation 層へ委譲する（単一の真実の源）。
"""
from presentation.web.api.version import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: アンダースコア始まり等も遅延委譲する
    import importlib

    module = importlib.import_module("presentation.web.api.version")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
