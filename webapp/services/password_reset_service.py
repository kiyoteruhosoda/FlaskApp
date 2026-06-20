"""後方互換リダイレクト: ``presentation.web.services.password_reset_service``.

実体は presentation 層に一本化する（重複コピーの放置による不整合を防ぐ）。
"""
from presentation.web.services.password_reset_service import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562: 非公開名も遅延委譲する
    import importlib

    module = importlib.import_module(
        "presentation.web.services.password_reset_service"
    )
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(
            f"module {__name__!r} has no attribute {name!r}"
        ) from exc
