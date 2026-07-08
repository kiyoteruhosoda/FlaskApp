# Progress — 進行中タスク

進行中・未着手のタスクのみを表で管理する（完了したら本ファイルから消し、重要な変更は
`CHANGELOG.md`／`history/` へ、設計判断は `decisions/`（ADR）へ移す）。

| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T9 | ユーザースイッチ（運用管理者ロールによる成り代わり） | ⬜未着手 | 中 | 大 |
| 2 | T11 | FastAPI 全面移行 — Flask UI 層移行・Flask 完全撤廃（Phase 2/3 後続） | 🚧進行中 | 大 | 大 |

---

## 詳細

- **T9 ユーザースイッチ** — 運用管理者ロールが他ユーザーに成り代わって画面を確認できる
  機能（impersonation）。監査ログ（誰がいつ誰に切り替えたか）と成り代わり中の表示、
  元ユーザーへ戻る導線が必須。認可・セッション設計に影響するため ADR を書いてから着手。

- **T11 FastAPI 全面移行** — Flask + Flask-Smorest から FastAPI への全面移行（ADR-0005）。
  Phase 1〜3（全 API エンドポイント移植・uvicorn 起動切替・Flask API 側登録無効化）は完了。
  詳細は `CHANGELOG.md` 参照。

  **残作業（Phase 2/3 後続）**:
  - Flask UI 層（テンプレート・Jinja2 ルート）の FastAPI + Jinja2 への移行
  - `flask-babel` → `babel` 直接使用への切り替え
  - `flask-login` セッション管理廃止・JWT 専一化
  - CDN/Blob admin API（`presentation/web/api/admin/cdn.py`, `blob.py`）の FastAPI 移植
  - Flask 完全撤廃（`flask`, `flask-smorest`, `flask-sqlalchemy`, `flask-migrate`,
    `flask-login`, `flask-babel` の削除）
  - Alembic 直接実行への移行（`flask db` コマンド廃止）
