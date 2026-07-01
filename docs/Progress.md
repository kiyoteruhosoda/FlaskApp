# Progress — 進行中タスク

進行中・未着手のタスクのみを表で管理する（完了したら本ファイルから消し、重要な変更は
`CHANGELOG.md`／`history/` へ、設計判断は `decisions/`（ADR）へ移す）。

| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T3 | 初回ログイン時パスワード強制変更フローの配線（既定 OFF） | 🚧進行中 | 小 | 中 |
| 2 | T4 | `bounded_contexts/email` と `bounded_contexts/email_sender` の重複統合 | 🟡要判断 | 中 | 中 |

---

## 詳細

- **T3 パスワード強制変更** — 設定フラグ `REQUIRE_PASSWORD_CHANGE_ON_FIRST_LOGIN`（既定
  OFF）は追加済。残: `user.must_change_password` 列＋マイグレーション、ログインゲート、
  フロント。既定 OFF のため未配線でも無害。
- **T4 email / email_sender 重複** — メール送信の実装が `bounded_contexts/email` と
  `bounded_contexts/email_sender` の2箇所に存在する（リネーム途中と思われる）。
  本番コード（`presentation/web/services/password_reset_service.py`）は
  `bounded_contexts.email` を使うが、`bounded_contexts/email/application/email_service.py`
  は値オブジェクト・インターフェース・ファクトリを `bounded_contexts.email_sender` から
  import しており、テストも大半が `email_sender` 側を対象にしている。どちらか一方に
  統合するか、責務を分けるか要判断。
