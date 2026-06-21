"""後方互換エイリアス: ``presentation.web.services.password_reset_service`` を唯一の実体として参照する。

DDD 移行で残った重複モジュール。``sys.modules`` 上で presentation 層の実体へ
エイリアスすることで、唯一の真実の源を共有する。これにより import 順序に
依存せず、モジュール属性のパッチ（テスト）や Blueprint の単一登録を保証する。
"""
import sys as _sys
import importlib as _importlib

_impl = _importlib.import_module("presentation.web.services.password_reset_service")
_sys.modules[__name__] = _impl
