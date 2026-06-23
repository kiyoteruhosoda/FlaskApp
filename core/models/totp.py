"""後方互換シム: 実体は
:mod:`bounded_contexts.totp.infrastructure.totp_models` へ移動した。

TOTP 認証情報モデルは TOTP bounded context の infrastructure 層に属する。既存の
``from core.models.totp import TOTPCredential`` を壊さないよう再公開する。
新規コードは context 側を直接 import すること。
"""

from bounded_contexts.totp.infrastructure.totp_models import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: __all__ 外の名前も遅延委譲する
    import importlib

    module = importlib.import_module(
        "bounded_contexts.totp.infrastructure.totp_models"
    )
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
