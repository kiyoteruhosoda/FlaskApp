"""後方互換シム: 実体は :mod:`shared.kernel.settings.system_settings_defaults` へ移動した。

永続化システム設定の既定値は DDD のカーネル層に集約する。既存の
``from core.system_settings_defaults import DEFAULT_APPLICATION_SETTINGS`` 等を
壊さないよう再公開する。
"""

from shared.kernel.settings.system_settings_defaults import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: __all__ 外の名前も遅延委譲する
    import importlib

    module = importlib.import_module(
        "shared.kernel.settings.system_settings_defaults"
    )
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover - 通常は到達しない
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
