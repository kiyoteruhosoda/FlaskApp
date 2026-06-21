# Vendored `flask_smorest`（カスタムフォーク）

このディレクトリは [`flask-smorest`](https://github.com/marshmallow-code/flask-smorest)
バージョン 0.46.2 をベースに、本プロジェクト独自の機能を加えた**カスタムフォーク**です。
単なるコピーではなく、以下のような上流に無い変更を含みます。

- `/api/overview`（`OPENAPI_OVERVIEW_PATH`）— エンドポイント一覧をインタラクティブに
  表示する独自の概要テーブル（`spec/templates/openapi_overview.html`）
- favicon を含むカスタム Swagger UI テンプレート（`spec/templates/swagger_ui.html`）
- エラースキーマ（配列形式の `error messages`）や手書きドキュメントの調整 など

## 読み込み順序に関する注意

リポジトリのルートが `sys.path` の先頭に来るため、`import flask_smorest` は
**この同梱フォークが pip インストール版より優先して読み込まれます**。
そのため、pip 版（`requirements.txt` の `flask-smorest`）を更新しても、
ここを削除しない限り実行時の挙動はこのフォークに従います。

上流の機能（`/api/overview` 等）に依存するテストがあるため、削除する場合は
それらの独自機能を `presentation/web` 側へ移植する必要があります。

The upstream project is distributed under the terms of the MIT License,
which is reproduced in `LICENSE`.
