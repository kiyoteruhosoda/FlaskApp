"""PO カタログに基づくメッセージ翻訳を担う。

Flask-Babel の ``gettext`` が ``.mo`` を生成しない運用（AGENTS.md §2）に合わせ、
``messages.po`` を直接読み込んでフォールバック翻訳を行う。``create_app()`` に
散在していた翻訳ロジックをここへ集約し、エラーハンドラ等からは本モジュールの
``translate_message`` を直接参照する（リフレクション経由の取得を排除する）。
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List

from babel.messages.pofile import read_po
from flask_babel import get_locale
from flask_babel import gettext as _

from shared.kernel.settings.settings import settings


def resolve_translation_directories() -> List[str]:
    """設定された翻訳ディレクトリを正規化した絶対/相対パス文字列で返す。"""

    directories_config = settings.babel_translation_directories
    candidates = [directory for directory in directories_config if directory]
    return [str(Path(candidate)) for candidate in candidates if candidate]


@lru_cache(maxsize=32)
def load_po_catalog(locale: str, directories: tuple[str, ...]) -> Dict[str, str]:
    """指定ロケールの ``messages.po`` を読み込み、msgid→msgstr の辞書を返す。"""

    catalog: Dict[str, str] = {}
    for directory in directories:
        po_path = Path(directory) / locale / "LC_MESSAGES" / "messages.po"
        if not po_path.exists():
            continue
        try:
            with po_path.open("rb") as buffer:
                parsed_catalog = read_po(buffer)
        except (OSError, ValueError):  # pragma: no cover - corrupted file handling
            continue
        for message in parsed_catalog:
            message_id = getattr(message, "id", None)
            message_str = getattr(message, "string", None)
            if message_id and message_str:
                catalog.setdefault(message_id, message_str)
    return catalog


def translate_message(message: str) -> str:
    """まず gettext で翻訳し、未訳なら現在ロケールの PO カタログで補完する。"""

    translated = _(message)
    if translated != message:
        return translated

    locale_obj = get_locale()
    locale_candidates: List[str] = []
    if locale_obj is not None:
        locale_str = str(locale_obj)
        if locale_str:
            locale_candidates.append(locale_str)
            if "_" in locale_str:
                base = locale_str.split("_", 1)[0]
                if base and base not in locale_candidates:
                    locale_candidates.append(base)

    default_locale = settings.babel_default_locale
    if isinstance(default_locale, str) and default_locale:
        if default_locale not in locale_candidates:
            locale_candidates.append(default_locale)

    directories = tuple(resolve_translation_directories())
    if not directories:
        return message

    for candidate in locale_candidates:
        candidate = candidate.strip()
        if not candidate:
            continue
        catalog = load_po_catalog(candidate, directories)
        if message in catalog:
            return catalog[message]

    return message
