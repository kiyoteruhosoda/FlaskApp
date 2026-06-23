"""後方互換シム: 実体は :mod:`shared.kernel.utils` へ移動した。

既存の import を壊さないよう再公開する。新規コードは正本を直接 import すること。
"""

from shared.kernel.utils import *  # noqa: F401,F403


def __getattr__(name):  # PEP 562
    import importlib
    module = importlib.import_module("shared.kernel.utils")
    try:
        return getattr(module, name)
    except AttributeError as exc:  # pragma: no cover
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
