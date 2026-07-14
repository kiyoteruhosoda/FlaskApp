# Progress — 進行中タスク

進行中・未着手のタスクのみを表で管理する（完了したら本ファイルから消し、重要な変更は
`CHANGELOG.md`／`history/` へ、設計判断は `decisions/`（ADR）へ移す）。

| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T9 | ユーザースイッチ（運用管理者ロールによる成り代わり） | ⬜未着手 | 中 | 大 |
| 2 | T12 | 初期管理者でログインし全画面を確認するフルスタックE2E | ⬜未着手 | 中 | 大 |
| 3 | T13 | state ストアを共有ストア（Redis等）へ置き換え | 🟡要判断 | 中 | 中 |

---

## 詳細

- **T9 ユーザースイッチ** — 運用管理者ロールが他ユーザーに成り代わって画面を確認できる
  機能（impersonation）。監査ログ（誰がいつ誰に切り替えたか）と成り代わり中の表示、
  元ユーザーへ戻る導線が必須。認可・セッション設計に影響するため ADR を書いてから着手。
  ※ `impersonation_audit_log` テーブルと `admin:impersonate` 権限コードは T11 で追加済み。

- **T12 初期管理者フルスタックE2E** — 既存の `frontend/e2e/*.spec.ts`（Playwright）は
  全てAPIをモックし実バックエンドを起動しない方針。これとは別に、実FastAPIサーバー
  ＋実DB（SQLite、`scripts/run_db_migrations.py` でスキーマ・マスタデータ投入）＋
  ビルド済みSPA（FastAPI自身が `frontend/build` を静的配信するため別途 `vite preview`
  は不要）を起動し、`admin@example.com` / `admin` で実際にログインして
  `App.tsx` の全ルート（約30画面）を巡回するフルスタックE2Eを追加する。
  既存スイートとは別設定ファイル（例: `playwright.fullstack.config.ts` /
  `e2e-fullstack/`）に分離し、重いテストとして別ジョブで実行する想定。
  - パラメータ付きルート（`/albums/:id`, `/sessions/:sessionId`,
    `/wiki/page/:slug` 等）は事前に管理者トークンで最小限のフィクスチャを
    API経由で作成してから遷移する。
  - 判定基準: コンソールエラー無し、権限エラー/500表示無し、各画面の
    `data-testid` ルート要素が表示されること。
  - 未決定事項: CI実行タイミング（毎PR/毎マージ/nightly）、フィクスチャ
    作成範囲。着手前に方針確定。

