"""後方互換シム: 実体は :mod:`shared.kernel.crypto.crypto` へ移動した。

DDD のカーネル層 (Shared Kernel) を単一の真実の源とするため、トークン暗号化
処理は ``shared.kernel.crypto.crypto`` に集約する。既存の
``from core.crypto import encrypt, decrypt`` 等を壊さないよう委譲する。
"""

from shared.kernel.crypto.crypto import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: ``_decode_key`` 等のアンダースコア名も遅延委譲する
    import importlib

    module = importlib.import_module("shared.kernel.crypto.crypto")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover - 通常は到達しない
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
