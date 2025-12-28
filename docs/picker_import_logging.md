# PickerImportタスクのログ追跡

## 概要

PickerImportタスクが以下の詳細ログを出力するようになりました：

## ログイベントタイプ

### 1. セッション関連
- `picker.session.start` - インポートセッション開始
- `picker.session.progress` - 進捗状況（10件ごと）
- `picker.session.complete` - インポートセッション完了
- `picker.session.error` - セッションレベルのエラー
- `picker.session.skip` - 既に完了済みセッションのスキップ

### 2. ファイル関連
- `picker.file.saved` - ファイル保存完了
- `picker.item.claim` - 個別アイテムの処理開始
- `picker.item.end` - 個別アイテムの処理完了

## ログ内容

### セッション開始ログ
```json
{
  "ts": "2025-08-28T10:30:00.000Z",
  "session_id": 123,
  "account_id": 456
}
```

### ファイル保存ログ
```json
{
  "ts": "2025-08-28T10:30:15.000Z",
  "selection_id": 789,
  "session_id": 123,
  "file_path": "/path/to/saved/file.jpg",
  "file_size": 2048576,
  "mime_type": "image/jpeg",
  "sha256": "abc123...",
  "original_filename": "IMG_20250828_103015.jpg"
}
```

### 進捗ログ
```json
{
  "ts": "2025-08-28T10:30:20.000Z",
  "session_id": 123,
  "progress": "10/50",
  "media_id": "google_media_id",
  "imported": 8,
  "duplicates": 1,
  "failed": 1
}
```

### セッション完了ログ
```json
{
  "ts": "2025-08-28T10:35:00.000Z",
  "session_id": 123,
  "account_id": 456,
  "status": "imported",
  "duration_seconds": 300.5,
  "imported": 45,
  "duplicates": 3,
  "failed": 2,
  "processed_total": 50
}
```

## ログ確認方法

### CLIスクリプトを使用
```bash
# 特定セッションのログを確認
python scripts/check_logs.py --session-id 123

# 最新20件のログを確認
python scripts/check_logs.py --last 20

# エラーログのみ確認
python scripts/check_logs.py --level ERROR

# 進捗ログのみ確認
python scripts/check_logs.py --event picker.session.progress

# JSON形式で出力
python scripts/check_logs.py --session-id 123 --json
```

### SQLで直接確認
```sql
-- 特定セッションのログ
SELECT * FROM log 
WHERE event LIKE 'picker.%' 
AND message LIKE '%"session_id": 123%' 
ORDER BY created_at;

-- 最新のインポートセッション
SELECT * FROM log 
WHERE event = 'picker.session.complete' 
ORDER BY created_at DESC 
LIMIT 5;

-- ファイル保存ログ
SELECT created_at, 
       JSON_EXTRACT(message, '$.file_path') as file_path,
       JSON_EXTRACT(message, '$.file_size') as file_size,
       JSON_EXTRACT(message, '$.mime_type') as mime_type
FROM log 
WHERE event = 'picker.file.saved' 
ORDER BY created_at DESC;
```

## 監視とデバッグ

### 1. タスクの実行状況を追跡
- セッション開始から完了までの時間
- 処理された件数と結果
- エラーの詳細

### 2. ファイルの保存状況を確認
- どのファイルがいつ保存されたか
- ファイルサイズとハッシュ値
- 保存パス

### 3. パフォーマンス分析
- 処理時間の分析
- 進捗状況の監視
- エラー率の計算

## トラブルシューティング

### よくある問題

1. **ファイルが見つからない**
   - `picker.file.saved`ログで保存パスを確認
   - ディスク容量をチェック

2. **処理が途中で止まる**
   - `picker.session.progress`ログで最後の処理位置を確認
   - `picker.session.error`ログでエラー内容を確認

3. **重複ファイルが多い**
   - セッション完了ログの`duplicates`フィールドを確認
   - 過去のインポート履歴と照合

### ログの保持期間

- ログは`log`テーブルに永続化されます
- 必要に応じて古いログの削除スクリプトを実行してください
- 重要なセッションのログは別途バックアップを推奨
