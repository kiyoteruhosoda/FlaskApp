"""`presentation/web/templating/translation.py` の単体テスト。

PO カタログ読込は ``.mo`` を生成しない運用（AGENTS.md §2）の要であり、
破損ファイルや欠落ロケールでも落ちないことが重要なため、ファイル入出力を
一時ディレクトリで再現して検証する。設定参照はモジュールの ``settings`` を
差し替え、アプリ生成・DB に依存しない安定したテストとする。
"""

import types

import pytest

from presentation.web.templating import translation
from presentation.web.templating.translation import (
    load_po_catalog,
    resolve_translation_directories,
)


def _write_po(directory, locale, body):
    lc_dir = directory / locale / "LC_MESSAGES"
    lc_dir.mkdir(parents=True, exist_ok=True)
    (lc_dir / "messages.po").write_text(body, encoding="utf-8")


@pytest.fixture(autouse=True)
def _clear_catalog_cache():
    # lru_cache がテスト間で結果を持ち越さないようにする。
    load_po_catalog.cache_clear()
    yield
    load_po_catalog.cache_clear()


class TestResolveTranslationDirectories:
    def test_filters_empty_entries(self, monkeypatch):
        monkeypatch.setattr(
            translation,
            "settings",
            types.SimpleNamespace(
                babel_translation_directories=["", "trans", None, "more"]
            ),
        )
        assert resolve_translation_directories() == ["trans", "more"]

    def test_empty_config_returns_empty(self, monkeypatch):
        monkeypatch.setattr(
            translation,
            "settings",
            types.SimpleNamespace(babel_translation_directories=[]),
        )
        assert resolve_translation_directories() == []


class TestLoadPoCatalog:
    def test_reads_msgid_msgstr(self, tmp_path):
        _write_po(
            tmp_path,
            "ja",
            'msgid "Hello"\nmsgstr "こんにちは"\n',
        )
        catalog = load_po_catalog("ja", (str(tmp_path),))
        assert catalog["Hello"] == "こんにちは"

    def test_missing_locale_returns_empty(self, tmp_path):
        assert load_po_catalog("ja", (str(tmp_path),)) == {}

    def test_first_directory_wins(self, tmp_path):
        first = tmp_path / "a"
        second = tmp_path / "b"
        _write_po(first, "ja", 'msgid "K"\nmsgstr "first"\n')
        _write_po(second, "ja", 'msgid "K"\nmsgstr "second"\n')
        catalog = load_po_catalog("ja", (str(first), str(second)))
        assert catalog["K"] == "first"

    def test_empty_translation_is_skipped(self, tmp_path):
        _write_po(tmp_path, "ja", 'msgid "K"\nmsgstr ""\n')
        assert "K" not in load_po_catalog("ja", (str(tmp_path),))


class TestTranslateMessage:
    def test_falls_back_to_po_catalog(self, tmp_path, monkeypatch):
        _write_po(tmp_path, "ja", 'msgid "Save"\nmsgstr "保存"\n')
        monkeypatch.setattr(
            translation,
            "settings",
            types.SimpleNamespace(
                babel_translation_directories=[str(tmp_path)],
                babel_default_locale="en",
            ),
        )
        # gettext は未訳（入力そのまま）を返すと仮定する。
        monkeypatch.setattr(translation, "_", lambda message: message)
        monkeypatch.setattr(translation, "get_locale", lambda: "ja")

        assert translation.translate_message("Save") == "保存"

    def test_returns_gettext_result_when_translated(self, monkeypatch):
        monkeypatch.setattr(translation, "_", lambda message: "DONE")
        assert translation.translate_message("Save") == "DONE"

    def test_returns_original_when_no_directories(self, monkeypatch):
        monkeypatch.setattr(
            translation,
            "settings",
            types.SimpleNamespace(
                babel_translation_directories=[],
                babel_default_locale="en",
            ),
        )
        monkeypatch.setattr(translation, "_", lambda message: message)
        monkeypatch.setattr(translation, "get_locale", lambda: "ja")
        assert translation.translate_message("Unknown") == "Unknown"

    def test_uses_base_language_fallback(self, tmp_path, monkeypatch):
        # ロケール "ja_JP" に対し基底言語 "ja" のカタログで補完できる。
        _write_po(tmp_path, "ja", 'msgid "Hi"\nmsgstr "やあ"\n')
        monkeypatch.setattr(
            translation,
            "settings",
            types.SimpleNamespace(
                babel_translation_directories=[str(tmp_path)],
                babel_default_locale="en",
            ),
        )
        monkeypatch.setattr(translation, "_", lambda message: message)
        monkeypatch.setattr(translation, "get_locale", lambda: "ja_JP")
        assert translation.translate_message("Hi") == "やあ"
