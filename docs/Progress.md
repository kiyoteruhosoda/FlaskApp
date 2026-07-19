# Progress — 進行中タスク

進行中・未着手のタスクのみを表で管理する（完了したら本ファイルから消し、重要な変更は
`CHANGELOG.md`／`history/` へ、設計判断は `decisions/`（ADR）へ移す）。

| 優先 | # | 概要 | 状態 | 影響度 | 工数 |
|---|---|---|---|---|---|
| 1 | T9 | ユーザースイッチ（運用管理者ロールによる成り代わり） | ⬜未着手 | 中 | 大 |
| 2 | T13 | state ストアを共有ストア（Redis等）へ置き換え | 🟡要判断 | 中 | 中 |
| 3 | T15 | メディアダウンロード API のストリーミング化 | ⬜未着手 | 大 | 中 |
| 4 | T16 | DB ログハンドラの非同期書き込み化 | ⬜未着手 | 中 | 中 |
| 5 | T17 | `log` テーブルのインデックス追加とエラーログ検索の改善 | ⬜未着手 | 中 | 小 |
| 6 | T18 | JWT 検証鍵のリクエスト毎 DB 解決をキャッシュ化 | 🟡要判断 | 中 | 小 |
| 7 | T19 | 重複ファイル取り込み時の再解析（二重ハッシュ）回避 | ⬜未着手 | 中 | 中 |
| 8 | T20 | Picker 選択保存 `_save_single_item` のバッチ化 | 🟡要判断 | 中 | 大 |

---

## 詳細

- **T9 ユーザースイッチ** — 運用管理者ロールが他ユーザーに成り代わって画面を確認できる
  機能（impersonation）。監査ログ（誰がいつ誰に切り替えたか）と成り代わり中の表示、
  元ユーザーへ戻る導線が必須。認可・セッション設計に影響するため ADR を書いてから着手。
  ※ `impersonation_audit_log` テーブルと `admin:impersonate` 権限コードは T11 で追加済み。

（T15〜T20 は PR #872 のパフォーマンスレビューで検出し、リスクや設計判断を伴うため
同 PR では見送ったフォローアップ）

- **T15 メディアダウンロード API のストリーミング化** —
  `presentation/fastapi/routers/media.py::_build_file_response` が動画原本・再生用
  ファイルを `f.read()` で全量メモリに読み込んで返している（Range リクエストも
  要求範囲を全量バッファ）。Gunicorn `--workers=2 --threads=4` では同時DL数件で
  メモリ枯渇し得る。`StreamingResponse` + チャンクイテレータへ置き換える
  （Range 対応は seek して指定長だけ yield するイテレータが必要）。
- **T16 DB ログハンドラの非同期書き込み化** —
  `shared/kernel/logging/db_log_handler.py` がログ1件ごとに同期で接続取得・INSERT・
  commit しており、async ハンドラ内で実行されるためイベントループを塞ぐ。
  CLAUDE.md は「DB へ非同期書き込み」を規定。stdlib の `QueueHandler` /
  `QueueListener` でキュー化し、バックグラウンドスレッドからバッチ INSERT する。
- **T17 `log` テーブルのインデックス追加とエラーログ検索の改善** —
  `log` に `created_at` / `level` のインデックスが無く、System Logs の
  `ORDER BY created_at DESC` がファイルソート、レベル一覧の `SELECT DISTINCT level`
  が全表スキャン。また Picker の選択エラーログ検索
  （`picker_session_service.py::_selection_error_logs`）が `message` への前方
  ワイルドカード LIKE ×2 で全表スキャンになっている。インデックス追加と、
  `selection_id` を索引可能なカラムへ持たせる（または event + 期間で絞る）改善。
- **T18 JWT 検証鍵のキャッシュ化** — `access_token_signing.py` が認証付き
  リクエストごとに検証鍵を DB / 設定から解決し（サーバ署名モードでは証明書ロード
  + `from_jwk` の鍵再構築も毎回）、`token_service.py` が `user.roles` を毎回 lazy
  load している。`(algorithm, kid)` キーの短TTLキャッシュ + 設定保存時の無効化を
  想定。鍵ローテーション・失効の即時性に関わるため ADR を書いてから着手。
- **T19 重複ファイル取り込み時の再解析回避** — 重複検出時に
  `_refresh_existing_media_metadata` が計算済みの `MediaFileAnalysis` を捨てて
  同一内容のファイルを再解析（SHA-256 + pHash + ffprobe）しており、再インポート時の
  取り込み時間が約2倍になる。`MetadataRefresher` プロトコルに解析結果を渡せるよう
  拡張し、解析対象パスが同じ場合のみ再利用する。
- **T20 Picker 選択保存のバッチ化** — `_save_single_item` がアイテム1件あたり
  約6回の DB 往復（存在確認×2・ロック付き再SELECT・flush×2・upsert）を行い、
  100件ページで約600ステートメント。ロック保持時間が延びておりデッドロック要因
  にもなる。ループ前に Media / PickerSelection / MediaItem を `IN` で一括プリ
  フェッチする設計だが、`with_for_update` のロック設計と IntegrityError リトライ
  経路に影響するため ADR を書いてから着手。

