# Progress — 進行中タスク

進行中・未着手のタスクのみを表で管理する（完了したら本ファイルから消し、重要な変更は
`CHANGELOG.md`／`history/` へ、設計判断は `decisions/`（ADR）へ移す）。

| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T9 | ユーザースイッチ（運用管理者ロールによる成り代わり） | ⬜未着手 | 中 | 大 |
| 2 | T11 | FastAPI 全面移行（Flask-Smorest → FastAPI、既存 Blueprint 含む） | ⬜未着手 | 大 | 大 |

---

## 詳細

- **T9 ユーザースイッチ** — 運用管理者ロールが他ユーザーに成り代わって画面を確認できる
  機能（impersonation）。監査ログ（誰がいつ誰に切り替えたか）と成り代わり中の表示、
  元ユーザーへ戻る導線が必須。認可・セッション設計に影響するため ADR を書いてから着手。
- **T11 FastAPI 全面移行** — Flask + Flask-Smorest から FastAPI への全面移行。認証
  （flask_login / JWT）、Blueprint 群（→ APIRouter）、Celery 連携、OpenAPI 自動生成の
  置き換え。移行順序・共存戦略を ADR で決めてから着手する。
