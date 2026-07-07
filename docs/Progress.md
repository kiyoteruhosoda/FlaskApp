# Progress — 進行中タスク

進行中・未着手のタスクのみを表で管理する（完了したら本ファイルから消し、重要な変更は
`CHANGELOG.md`／`history/` へ、設計判断は `decisions/`（ADR）へ移す）。

| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T3 | 初回ログイン時パスワード強制変更フローの配線（既定 OFF） | 🚧進行中 | 小 | 中 |
| 2 | T4 | `bounded_contexts/email` と `bounded_contexts/email_sender` の重複統合 | 🟡要判断 | 中 | 中 |
| 3 | T5 | Photo Exports（/admin/photo-exports）画面が未実装（プレースホルダーのみ） | ⬜未着手 | 小 | 中 |
| 4 | T7 | ユーザーとグループの紐づけ画面 | ⬜未着手 | 中 | 中 |
| 5 | T8 | グループとロールの紐づけ | ⬜未着手 | 中 | 中 |
| 6 | T9 | ユーザースイッチ（運用管理者ロールによる成り代わり） | ⬜未着手 | 中 | 大 |
| 7 | T10 | ロール設計見直し（運用管理者・運用者・システムオーナーの分離） | 🟡要判断 | 大 | 中 |
| 8 | T11 | FastAPI 移行 | 🟡要判断 | 大 | 大 |

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
- **T5 Photo Exports 未実装** — `frontend/src/pages/PhotoExportsPage.tsx`（`/admin/photo-exports`）
  は `t('Export management is not yet implemented.')` を表示するだけのプレースホルダー。
  エクスポート機能（対象選択・形式・ダウンロード導線）の実装が必要。
- **T7 ユーザーとグループの紐づけ** — Groups 画面（`/admin/groups`）はグループ CRUD のみで、
  ユーザーをグループへ所属させる UI がない（バックエンドの `memberIds` 更新 API は存在）。
  Users 画面またはグループ詳細からメンバーを編集できるようにする。
- **T8 グループとロールの紐づけ** — 現状ロールはユーザーに直接付与する設計。グループに
  ロールを付与し、所属ユーザーへ波及させる仕組み（モデル・マイグレーション・UI）が必要。
  T10 のロール設計見直しと合わせて検討する。
- **T9 ユーザースイッチ** — 運用管理者ロールが他ユーザーに成り代わって画面を確認できる
  機能（impersonation）。監査ログ（誰がいつ誰に切り替えたか）と成り代わり中の表示、
  元ユーザーへ戻る導線が必須。認可・セッション設計に影響するため ADR を書いてから着手。
- **T10 ロール設計見直し** — 現行の admin/manager/member/guest を、運用管理者・運用者・
  システムオーナーに分けるべきか検討。権限コード（scope）の粒度は維持し、ロール＝権限の
  束ね直しとして設計する。決定は ADR に残し `shared/domain/auth/master_data.py` を更新する。
- **T11 FastAPI 移行** — Flask + Flask-Smorest から FastAPI への移行検討。認証
  （flask_login / JWT）、Blueprint 群、Celery 連携、OpenAPI 自動生成の置き換え範囲が
  大きいため、段階移行の方針（新規 API のみ FastAPI 等）を ADR で決めてから着手。
