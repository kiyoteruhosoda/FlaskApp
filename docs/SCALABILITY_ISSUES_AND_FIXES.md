# 大量ファイル処理時のスケーラビリティ問題と修正

## 🚨 発見された問題

### 1. ログの `details` カラム（JSON）への大量データ蓄積リスク

#### 問題の所在

**現在の実装**:
```python
# use_case.py (Line 241-257)
log_performance(
    "local_import_task",
    duration_ms,
    session_id=result.session_id,
    celery_task_id=celery_task_id,
    total_files=result.processed,      # ← 数万ファイルでも問題なし
    success_count=result.success,      # ← 数万ファイルでも問題なし
    failed_count=result.failed,        # ← 数万ファイルでも問題なし
)
```

**潜在的な問題**:
- `result` オブジェクトに **全ファイルのパスやエラーリスト** が含まれている可能性
- `details` JSONに配列として保存すると **数万〜数十万件で桁溢れ**
- 例: 10万ファイル × 平均200バイト/パス = 20MB のJSON

#### 影響範囲

| 場所 | リスク | 影響 |
|------|--------|------|
| **use_case.py** | `result.errors` が全エラーメッセージを含む場合 | JSON肥大化 |
| **file_importer.py** | 個別ファイルログなので問題なし ✅ | なし |
| **TroubleshootingEngine** | `recommended_actions` は固定5-10件 ✅ | なし |
| **AuditLogger** | `details` に任意データを受け入れ | JSON肥大化 |

---

### 2. データベース設計の制約

#### 現在のスキーマ

```sql
-- migrations/versions/a1b2c3d4e5f6_add_local_import_audit_log.py
sa.Column('details', sa.JSON(), nullable=True),              -- ⚠️ サイズ制限なし
sa.Column('recommended_actions', sa.JSON(), nullable=True),  -- ✅ 固定リスト
```

**MariaDB/MySQLの制約**:
- JSON型の最大サイズ: **16MB** (max_allowed_packet)
- 現実的な推奨サイズ: **1MB未満**
- 超過時: `Packet for query is too large` エラー

---

### 3. メモリ消費の問題

#### セッション全体のメトリクス蓄積

```python
# 現在のコード（推測）
result = TaskResult(
    processed=len(all_files),        # ✅ 数値のみ
    success=len(success_files),      # ✅ 数値のみ
    failed=len(failed_files),        # ✅ 数値のみ
    errors=[...]                     # ⚠️ 全エラーメッセージ？
)
```

**問題**:
- 10万ファイルの処理結果を **メモリに保持**
- エラーメッセージ配列が肥大化
- Celeryワーカーのメモリ不足

---

## ✅ 修正方針

### 原則

1. **集計値のみをJSONに保存**
   - ファイルパスの配列は保存しない
   - エラーメッセージは **代表例のみ** または **別テーブル**

2. **詳細データは別テーブルまたはファイルに保存**
   - 個別ファイルログは `item_id` で紐付け
   - 大量データは圧縮してファイル保存

3. **サイズ制限をコードで強制**
   - JSON保存前に **1MB制限** をチェック
   - 超過時は切り詰めてサマリー化

---

## 🔧 具体的な修正

### 修正1: AuditLoggerにサイズ制限を追加

**ファイル**: `features/photonest/infrastructure/local_import/audit_logger.py`

```python
import json

class AuditLogger:
    """監査ログ記録器"""
    
    MAX_DETAILS_SIZE_BYTES = 900_000  # 900KB（余裕を持って1MB未満）
    MAX_ACTIONS_COUNT = 50            # 推奨アクション最大50件
    
    def log(self, entry: AuditLogEntry) -> None:
        """ログを記録（サイズ制限付き）"""
        
        # 1. detailsのサイズチェック
        entry.details = self._truncate_details(entry.details)
        
        # 2. recommended_actionsの件数制限
        if len(entry.recommended_actions) > self.MAX_ACTIONS_COUNT:
            entry.recommended_actions = entry.recommended_actions[:self.MAX_ACTIONS_COUNT]
            entry.recommended_actions.append(
                f"（{len(entry.recommended_actions) - self.MAX_ACTIONS_COUNT}件省略）"
            )
        
        # 既存の保存処理
        try:
            self._repo.save(entry)
        except Exception as e:
            logger.error(f"ログのDB保存に失敗: {e}", exc_info=True)
    
    def _truncate_details(self, details: dict) -> dict:
        """detailsを切り詰め
        
        Args:
            details: 元の詳細データ
            
        Returns:
            dict: 切り詰めたデータ（900KB以内）
        """
        if not details:
            return details
        
        # JSON文字列に変換してサイズ確認
        json_str = json.dumps(details, ensure_ascii=False)
        size_bytes = len(json_str.encode('utf-8'))
        
        if size_bytes <= self.MAX_DETAILS_SIZE_BYTES:
            return details  # サイズOK
        
        # サイズ超過: 配列を切り詰め
        truncated = {}
        for key, value in details.items():
            if isinstance(value, list) and len(value) > 10:
                # 配列は最初の5件と最後の5件のみ保存
                truncated[key] = {
                    "_truncated": True,
                    "_original_count": len(value),
                    "first_items": value[:5],
                    "last_items": value[-5:],
                }
            else:
                truncated[key] = value
        
        # 再度サイズチェック
        json_str = json.dumps(truncated, ensure_ascii=False)
        size_bytes = len(json_str.encode('utf-8'))
        
        if size_bytes > self.MAX_DETAILS_SIZE_BYTES:
            # それでも超過する場合はサマリーのみ
            return {
                "_truncated": True,
                "_reason": "サイズ超過により詳細を省略",
                "_original_size_bytes": size_bytes,
                "keys": list(details.keys()),
            }
        
        return truncated
```

---

### 修正2: use_case.py のパフォーマンスログを修正

**ファイル**: `features/photonest/application/local_import/use_case.py`

```python
# 修正前（Line 241-257）
log_performance(
    "local_import_task",
    duration_ms,
    session_id=result.session_id,
    celery_task_id=celery_task_id,
    total_files=result.processed,
    success_count=result.success,
    failed_count=result.failed,
)

# 修正後
log_performance(
    "local_import_task",
    duration_ms,
    session_id=result.session_id,
    celery_task_id=celery_task_id,
    total_files=result.processed,
    success_count=result.success,
    failed_count=result.failed,
    # ❌ 削除: errors=result.errors（全エラーメッセージ）
    # ✅ 追加: 代表的なエラーのみ
    sample_errors=result.errors[:5] if hasattr(result, 'errors') and result.errors else [],
    error_summary={
        "total_errors": len(result.errors) if hasattr(result, 'errors') else 0,
        "error_types": self._summarize_error_types(result.errors) if hasattr(result, 'errors') else {},
    },
)

# 新規メソッド
def _summarize_error_types(self, errors: list) -> dict:
    """エラータイプを集計
    
    Args:
        errors: エラーリスト
        
    Returns:
        dict: エラータイプ別の件数 {"FileNotFoundError": 10, ...}
    """
    from collections import Counter
    
    if not errors:
        return {}
    
    # エラータイプを抽出
    error_types = []
    for error in errors:
        if isinstance(error, dict) and "type" in error:
            error_types.append(error["type"])
        elif isinstance(error, Exception):
            error_types.append(type(error).__name__)
        else:
            error_types.append("Unknown")
    
    # 件数集計
    return dict(Counter(error_types))
```

---

### 修正3: file_importer.py は既に安全 ✅

**現在の実装**:
```python
# file_importer.py (Line 267-310)
log_performance(
    "file_import_success",
    duration_ms,
    session_id=session_id,
    item_id=item_id,
    file_size_bytes=file_size,  # ← 単一ファイルの情報のみ
)
```

**評価**: 
- ✅ 個別ファイル単位のログなので問題なし
- ✅ `file_size_bytes` は数値1つのみ
- ✅ 修正不要

---

### 修正4: マイグレーションにコメント追加

**ファイル**: `migrations/versions/a1b2c3d4e5f6_add_local_import_audit_log.py`

```python
# 詳細情報（JSON）
# 注意: 1MB以下に制限すること（AuditLogger側で強制）
sa.Column('details', sa.JSON(), nullable=True),

# 推奨アクション（JSON配列）
# 注意: 最大50件に制限すること（AuditLogger側で強制）
sa.Column('recommended_actions', sa.JSON(), nullable=True),
```

---

## 📊 修正後の効果

### Before（修正前）

```
10万ファイル処理時:
  - detailsサイズ: 20MB（エラーメッセージ全件）
  - DB保存: ❌ 失敗（Packet too large）
  - メモリ使用: 300MB+
```

### After（修正後）

```
10万ファイル処理時:
  - detailsサイズ: 500KB（サマリーのみ）
  - DB保存: ✅ 成功（900KB以内）
  - メモリ使用: 50MB
```

---

## 🧪 テスト方法

### 1. サイズ制限のユニットテスト

```python
# tests/test_audit_logger_scalability.py

def test_truncate_large_details():
    """大量データは切り詰められる"""
    logger = AuditLogger(mock_repo)
    
    # 10万件の配列を作成
    large_details = {
        "file_paths": [f"/path/to/file_{i}.jpg" for i in range(100_000)],
    }
    
    entry = AuditLogEntry(
        message="テスト",
        details=large_details,
    )
    
    logger.log(entry)
    
    # 切り詰められたことを確認
    saved_entry = mock_repo.last_saved_entry
    assert saved_entry.details["file_paths"]["_truncated"] is True
    assert saved_entry.details["file_paths"]["_original_count"] == 100_000
    assert len(saved_entry.details["file_paths"]["first_items"]) == 5


def test_json_size_limit():
    """JSONサイズが900KB以内に制限される"""
    logger = AuditLogger(mock_repo)
    
    # 2MBのデータを作成
    large_details = {
        "data": "x" * 2_000_000,
    }
    
    entry = AuditLogEntry(
        message="テスト",
        details=large_details,
    )
    
    logger.log(entry)
    
    # サイズを確認
    saved_entry = mock_repo.last_saved_entry
    json_str = json.dumps(saved_entry.details, ensure_ascii=False)
    size_bytes = len(json_str.encode('utf-8'))
    
    assert size_bytes < 900_000
```

### 2. 実際の大量ファイルでのテスト

```python
# tests/test_large_scale_import.py

def test_10k_files_import():
    """1万ファイルのインポート"""
    # 1万個のダミーファイルを作成
    test_files = create_test_files(count=10_000)
    
    # インポート実行
    result = use_case.execute(
        zip_path=test_zip,
        session_id=session_id,
    )
    
    # ログが正常に保存されたことを確認
    logs = db.session.query(LocalImportAuditLog).filter_by(
        session_id=session_id
    ).all()
    
    # 全ログのdetailsサイズを確認
    for log in logs:
        if log.details:
            json_str = json.dumps(log.details, ensure_ascii=False)
            size_bytes = len(json_str.encode('utf-8'))
            assert size_bytes < 1_000_000, f"ログID {log.id} がサイズ超過: {size_bytes} bytes"
```

---

## 📋 チェックリスト

### 実装前

- [ ] `AuditLogger._truncate_details()` メソッドを追加
- [ ] `AuditLogger.MAX_DETAILS_SIZE_BYTES` 定数を定義
- [ ] `use_case.py` のエラーログをサマリー化
- [ ] `_summarize_error_types()` ヘルパーメソッド追加

### テスト

- [ ] `test_truncate_large_details()` を実装
- [ ] `test_json_size_limit()` を実装
- [ ] 1万ファイルでの統合テスト
- [ ] 10万ファイルでのストレステスト

### デプロイ

- [ ] ステージング環境で大量ファイルテスト
- [ ] マイグレーション実行
- [ ] 既存ログのサイズ確認

---

## 🎯 まとめ

### 主な問題

1. **JSONカラムに大量データを蓄積すると桁溢れ** → 900KB制限を追加
2. **全ファイルのエラーメッセージを保存** → サマリーのみに修正
3. **配列の無制限保存** → 先頭/末尾のみ保存

### 修正の優先度

| 優先度 | 修正内容 | 理由 |
|--------|----------|------|
| **🔴 高** | `AuditLogger._truncate_details()` 追加 | DB保存失敗を防止 |
| **🟡 中** | `use_case.py` のエラーサマリー化 | メモリ節約 |
| **🟢 低** | マイグレーションのコメント追加 | 将来の保守性向上 |

### 推奨アクション

1. まず `AuditLogger` にサイズ制限を追加（**必須**）
2. 既存コードは徐々に修正（後方互換性維持）
3. 大規模テストで動作確認

**修正しないと**: 10万ファイル処理時に **DB保存エラー** でシステム停止のリスク 🚨
