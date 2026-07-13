"""空文字の環境変数が DB 設定値・デフォルト値を握りつぶさないことの回帰テスト。

Docker の ``env_file`` 等で ``GOOGLE_OAUTH_REDIRECT_ORIGIN=`` のように空定義された
環境変数を「設定済み」と扱うと、管理画面で保存した値が消えたように見え（読み取り
専用の空欄表示になり）、実行時にもリクエスト由来のホストへフォールバックしていた。
管理画面で編集可能な設定キー（``DEFAULT_APPLICATION_SETTINGS``）では、空の環境変数を
「未設定」とみなし DB 値・デフォルト値へフォールバックする。
"""
from __future__ import annotations

import pytest

from shared.kernel.settings.settings import ApplicationSettings


@pytest.mark.unit
def test_blank_env_falls_back_to_default_for_config_key():
    """空文字の環境変数は編集可能キーではデフォルト値へフォールバックする。"""
    isolated = ApplicationSettings(env={"BABEL_DEFAULT_LOCALE": ""})
    # 空 env のため settings._get はデフォルト ("en") を返す
    assert isolated.get("BABEL_DEFAULT_LOCALE", "en") == "en"


@pytest.mark.unit
def test_blank_env_redirect_origin_is_treated_as_unset():
    """空文字の GOOGLE_OAUTH_REDIRECT_ORIGIN は未設定として扱う。"""
    isolated = ApplicationSettings(env={"GOOGLE_OAUTH_REDIRECT_ORIGIN": ""})
    assert isolated.google_oauth_redirect_origin == ""


@pytest.mark.unit
def test_nonblank_env_still_wins():
    """空でない環境変数は従来どおり最優先される。"""
    isolated = ApplicationSettings(
        env={"GOOGLE_OAUTH_REDIRECT_ORIGIN": "https://from-env.example.com"}
    )
    assert isolated.google_oauth_redirect_origin == "https://from-env.example.com"


@pytest.mark.unit
def test_blank_env_does_not_affect_bootstrap_keys():
    """DEFAULT_APPLICATION_SETTINGS に無いブートストラップ用キーは対象外。

    空でも「明示的な空指定」を尊重する（例: DATABASE_URI）。
    """
    isolated = ApplicationSettings(env={"DATABASE_URI": ""})
    # 空文字がそのまま返る（デフォルトのフォールバックには入らない）
    assert isolated.get("DATABASE_URI", "sqlite:///x.db") == ""
