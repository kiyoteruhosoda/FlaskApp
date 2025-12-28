# Celeryワーカーとタスクの役割まとめ

## 目的
Celeryを使った非同期処理では、ワーカーとタスクが明確に役割分担を行うことで安定したジョブ実行と監視が可能になります。このドキュメントでは、本プロジェクトにおけるそれぞれの責務と、関連する設定・コード上のポイントを整理します。

## Celeryワーカーの役割
- **実行プロセスのホスト**: `celery -A cli.src.celery.tasks worker --loglevel=info` で起動し、登録済みタスクを待ち受けて実行します。Beat（スケジューラ）も `celery -A cli.src.celery.tasks beat --loglevel=info` で並行起動し、定期タスクを投入します。
- **Flaskアプリコンテキストの初期化**: ワーカー起動時に `cli.src.celery.celery_app.create_app()` でFlaskアプリを生成し、`ContextTask` を通じて各タスクの実行毎にアプリケーションコンテキストとDBセッションを確保します。
- **ロギングと監査の統合**: `setup_celery_logging()` がワーカー側で呼び出され、コンソール出力とDBロガー（`WorkerDBLogHandler`）を紐付け、`celery.task`系ロガーの整備とルートロガーのしきい値制御を行います。
- **タスクライフサイクル管理**: `ContextTask.__call__` では実行前後・リトライ・失敗時の情報を `CeleryTaskRecord` と `JobSync` に保存し、`celery.task.lifecycle` ロガーへイベントを記録します。これにより管理UIやスクリプトからタスク状況を一元参照できます。

## Celeryタスクの役割
- **実際の業務処理を実装**: `cli/src/celery/tasks.py` で定義された `dummy_long_task`、`thumbs_generate_task`、`picker_import_item_task` などが実処理（メディアサムネイル生成、ピッカーインポート、ローカル取り込み等）を担当します。各タスクは `@celery.task` デコレータで登録され、ワーカーから呼び出されます。
- **アプリケーションコードとの橋渡し**: タスク本体は `core.tasks` や `features.certs.tasks` といったドメインロジックを呼び出し、Celery側で例外捕捉やロギングを行います。`ContextTask` の `self.log_error` や `log_task_info()` を用いて、成功・失敗・リトライなどの結果をロガーとDBに反映します。
- **メタデータと結果の保存**: タスクの戻り値は `ContextTask` によって `CeleryTaskRecord.set_result()` に格納されます。これにより、`python -m cli.src.celery.inspect_tasks` などのヘルパースクリプトから詳細な結果確認が可能になります。
- **スケジュール実行のエントリポイント**: Beatで登録された `picker_import.watchdog` や `session_recovery.cleanup_stale_sessions` などのタスクは、ワーカーに投入される定期ジョブのエントリポイントとなり、システム保守処理を自動化します。

## 運用時のポイント
- **ワーカー・Beatの常時稼働**: バックグラウンド処理や自動リカバリ機能を活かすため、ワーカーとBeatの両方を常時稼働させてください。
- **タスク監視**: タスク実行履歴や待機中ジョブは `cli/src/celery/inspect_tasks` モジュール経由で確認できます。DBに保存された `CeleryTaskRecord` と `JobSync` 情報を活用して、障害調査やリトライ状況の把握を行いましょう。
- **コード変更時の注意**: 新しいタスクを追加する場合は `cli/src/celery/tasks.py` で定義したあと、必要に応じてBeatスケジュールやドメインロジックの依存モジュールを更新し、`ContextTask` のライフサイクル管理に乗るようにしてください。

## 参考リンク
- `cli/src/celery/celery_app.py`: Celeryアプリ初期化、コンテキスト管理、ロギング設定の実装。
- `cli/src/celery/tasks.py`: 登録されているCeleryタスクと各タスクのロジック。
- `README.md`「Celeryワーカー（必須）」: 運用時の起動コマンドと注意事項。
