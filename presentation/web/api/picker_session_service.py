"""後方互換シム: 実体は
:mod:`bounded_contexts.picker_import.application.picker_session_service` へ移動した。

``PickerSessionService`` はピッカーセッションのアプリケーションロジックであり、
本来 ``picker_import`` bounded context の application 層に属する。既存の
``from presentation.web.api.picker_session_service import ...`` を壊さないよう
同名を再公開する。新規コードは context 側を直接 import すること。
"""

from bounded_contexts.picker_import.application.picker_session_service import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: __all__ 外の名前（_helpers 等）も遅延委譲する
    import importlib

    module = importlib.import_module(
        "bounded_contexts.picker_import.application.picker_session_service"
    )
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
