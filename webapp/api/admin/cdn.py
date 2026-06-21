"""後方互換エイリアス: ``presentation.web.api.admin.cdn`` を唯一の実体として参照する。

DDD 移行で presentation 層へ実体を移設した。``sys.modules`` 上でエイリアス
することで、唯一の真実の源を共有し import 順序や Blueprint 二重登録の問題を防ぐ。
"""
import sys as _sys
import importlib as _importlib

_impl = _importlib.import_module("presentation.web.api.admin.cdn")
_sys.modules[__name__] = _impl
