# Progress — 進行中タスク

進行中・未着手のタスクのみを表で管理する（完了したら本ファイルから消し、重要な変更は
`CHANGELOG.md`／`history/` へ、設計判断は `decisions/`（ADR）へ移す）。

| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T4 | `bounded_contexts/email` を `email_sender` に統合・`email` を削除 | ⬜未着手 | 中 | 中 |
| 2 | T8 | グループとロールの紐づけ | ⬜未着手 | 中 | 中 |
| 3 | T9 | ユーザースイッチ（運用管理者ロールによる成り代わり） | ⬜未着手 | 中 | 大 |
| 4 | T11 | FastAPI 全面移行（Flask-Smorest → FastAPI、既存 Blueprint 含む） | ⬜未着手 | 大 | 大 |

---

## 詳細

- **T4 email_sender 統合** — `bounded_contexts/email` を削除し、すべてを
  `bounded_contexts/email_sender` に一本化する。本番コード
  （`presentation/web/services/password_reset_service.py` 等）の import パスを
  `bounded_contexts.email_sender` に変更する。テストはすでに大半が `email_sender` 側を
  対象にしているため変更は最小限。
- **T8 グループとロールの紐づけ** — 現状ロールはユーザーに直接付与する設計。グループに
  ロールを付与し、所属ユーザーへ波及させる仕組み（モデル・マイグレーション・UI）が必要。
- **T9 ユーザースイッチ** — 運用管理者ロールが他ユーザーに成り代わって画面を確認できる
  機能（impersonation）。監査ログ（誰がいつ誰に切り替えたか）と成り代わり中の表示、
  元ユーザーへ戻る導線が必須。認可・セッション設計に影響するため ADR を書いてから着手。
- **T11 FastAPI 全面移行** — Flask + Flask-Smorest から FastAPI への全面移行。認証
  （flask_login / JWT）、Blueprint 群（→ APIRouter）、Celery 連携、OpenAPI 自動生成の
  置き換え。移行順序・共存戦略を ADR で決めてから着手する。
