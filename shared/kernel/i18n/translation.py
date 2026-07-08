"""Flask 非依存の国際化（i18n）モジュール。

flask-babel を使わずに Babel の GNUTranslations を直接使用する。
翻訳ファイルは ``presentation/web/translations/`` に格納されている。

使用方法::

    from shared.kernel.i18n.translation import gettext as _
    msg = _("Login")

ロケール選択の優先順位:
    1. スレッドローカルで明示的にセットされた値
    2. 環境変数 ``BABEL_DEFAULT_LOCALE``
    3. デフォルト（``ja``）
"""
from __future__ import annotations

import logging
import threading
from gettext import GNUTranslations, NullTranslations
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 翻訳ファイルのディレクトリ
_TRANSLATIONS_DIR = Path(__file__).resolve().parent / "translations"

# スレッドローカルなロケール
_thread_local = threading.local()

# 翻訳キャッシュ（ロケール → Translations）
_translation_cache: dict[str, GNUTranslations | NullTranslations] = {}


def _load_translation(locale: str) -> GNUTranslations | NullTranslations:
    """指定ロケールの翻訳オブジェクトをロードする（キャッシュあり）。"""
    if locale in _translation_cache:
        return _translation_cache[locale]

    locale_dir = _TRANSLATIONS_DIR / locale / "LC_MESSAGES"
    mo_file = locale_dir / "messages.mo"

    if mo_file.exists():
        try:
            with open(mo_file, "rb") as f:
                translation = GNUTranslations(f)
            _translation_cache[locale] = translation
            return translation
        except Exception as exc:
            logger.warning("翻訳ファイルのロードに失敗しました locale=%s: %s", locale, exc)

    # フォールバック: NullTranslations（メッセージをそのまま返す）
    null = NullTranslations()
    _translation_cache[locale] = null
    return null


def get_locale() -> str:
    """現在のロケールを返す。"""
    # スレッドローカルから取得
    locale = getattr(_thread_local, "locale", None)
    if locale:
        return locale

    # 環境変数からフォールバック
    import os
    return os.environ.get("BABEL_DEFAULT_LOCALE", "ja")


def set_locale(locale: str) -> None:
    """現在スレッドのロケールをセットする。"""
    _thread_local.locale = locale


def gettext(message: str) -> str:
    """メッセージを現在のロケールで翻訳する。"""
    locale = get_locale()
    translation = _load_translation(locale)
    return translation.gettext(message)


# Flask-Babel 互換エイリアス
_ = gettext


def lazy_gettext(message: str) -> str:
    """遅延評価版 gettext（flask-babel の lazy_gettext 互換）。

    このモジュールでは通常の gettext と同じ動作をする。
    モジュール定数に使用する場合は、アクセス時点のロケールで翻訳される。
    """
    return gettext(message)


class ForceLocale:
    """コンテキストマネージャ: 一時的にロケールを強制する。

    使用例::

        with ForceLocale("en"):
            message = _("Login")
    """

    def __init__(self, locale: str) -> None:
        self._locale = locale
        self._previous: Optional[str] = None

    def __enter__(self) -> "ForceLocale":
        self._previous = getattr(_thread_local, "locale", None)
        set_locale(self._locale)
        return self

    def __exit__(self, *_args: object) -> None:
        if self._previous is not None:
            set_locale(self._previous)
        else:
            _thread_local.locale = None


def force_locale(locale: str) -> ForceLocale:
    """flask-babel の force_locale 互換コンテキストマネージャ。"""
    return ForceLocale(locale)


__all__ = [
    "gettext",
    "_",
    "lazy_gettext",
    "get_locale",
    "set_locale",
    "force_locale",
    "ForceLocale",
]
