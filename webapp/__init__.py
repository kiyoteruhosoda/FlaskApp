# Backward compatibility redirect for webapp module
# This module has been moved to presentation.web
# Import everything from the new location

from presentation.web import *  # noqa: F403, F401


def __getattr__(name):
    """`from presentation.web import *` で取り込めない名前を委譲する。

    ``import *`` はアンダースコア始まりの名前（例: ``_apply_persisted_settings``）を
    再エクスポートしない。ここで遅延的に委譲することで後方互換を保ちつつ、
    初期化途中の循環 import でも失敗しないようにする（PEP 562）。
    """
    import presentation.web as _presentation_web

    try:
        return getattr(_presentation_web, name)
    except AttributeError as exc:  # pragma: no cover - 通常は到達しない
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc

