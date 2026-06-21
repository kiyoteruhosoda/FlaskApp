# Phase 2/3 統合ガイド

## 📋 概要

このガイドでは、Local Import状態管理システムのPhase 2（ログ追加）とPhase 3（完全統合）の実装内容を説明します。

---

## ✅ Phase 2: 完了した統合

### 統合済みファイル

#### 1. **use_case.py** - メインタスク処理

**場所**: `features/photonest/application/local_import/use_case.py`

**追加内容**:
```python
# インポート追加
from features.photonest.infrastructure.local_import.logging_integration import (
    init_audit_logger,
    log_with_audit,
    log_performance,
)

# execute()メソッドに追加
- 処理開始時: log_with_audit() で開始ログ
- 処理完了時: log_performance() でパフォーマンス記録
- 処理完了時: log_with_audit() で完了ログ
```

**変更箇所**:
- Line 16-19: インポート追加
- Line 43-47: 処理開始ログ
- Line 241-257: 完了ログとパフォーマンス記録

---

#### 2. **file_importer.py** - ファイル取り込み処理

**場所**: `features/photonest/application/local_import/file_importer.py`

**追加内容**:
```python
# インポート追加
from features.photonest.infrastructure.local_import.logging_integration import (
    log_file_operation,
    log_duplicate_check,
    log_error_with_actions,
    log_performance,
)

# import_file()メソッドに追加
- 処理開始時: log_file_operation() でファイル操作ログ
- 重複チェック後: log_duplicate_check() で重複検知ログ
- 成功時: log_performance() + log_file_operation()
- エラー時: log_error_with_actions() で推奨アクション付きエラーログ
```

**変更箇所**:
- Line 19-24: インポート追加
- Line 177-182: パフォーマンス計測とitem_id生成
- Line 191-196: ファイル処理開始ログ
- Line 233-242: 重複チェックログ
- Line 244-258: 重複時のパフォーマンスログ
- Line 267-282: 成功時のパフォーマンスとファイル操作ログ
- Line 284-307: エラー時の詳細ログと推奨アクション

---

### Phase 2の効果

#### ✅ 実装された機能

1. **完全なトレーサビリティ**
   - すべてのファイル処理が `local_import_audit_log` テーブルに記録
   - session_id と item_id で追跡可能

2. **パフォーマンス計測**
   - 各処理の所要時間を自動記録
   - ファイルサイズとの相関分析が可能

3. **重複検知ログ**
   - 重複チェック結果を明示的に記録
   - ハッシュ値と一致タイプを保存

4. **エラー診断と推奨アクション**
   - TroubleshootingEngineによる自動診断
   - エラーごとに適切な対応方法を提示

#### 📊 ログ出力例

```sql
-- セッションの処理フロー確認
SELECT timestamp, category, message, duration_ms
FROM local_import_audit_log
WHERE session_id = 'local_import_abc123'
ORDER BY timestamp;

-- パフォーマンス分析
SELECT 
  category,
  AVG(duration_ms) as avg_ms,
  MAX(duration_ms) as max_ms,
  COUNT(*) as count
FROM local_import_audit_log
WHERE category = 'performance'
GROUP BY category;

-- エラー分析
SELECT 
  error_type,
  COUNT(*) as count,
  recommended_actions
FROM local_import_audit_log
WHERE level = 'ERROR'
GROUP BY error_type, recommended_actions;
```

---

## 🚀 Phase 3: 完全統合（参考実装）

### Phase 3の特徴

Phase 3では、**with文**を使った状態管理により、以下が自動化されます：

1. **自動状態遷移** - 処理フローに応じて自動的に状態が変化
2. **自動エラーハンドリング** - 例外発生時に自動的にFAILED状態へ
3. **自動ログ記録** - 状態遷移とパフォーマンスを自動記録
4. **整合性チェック** - セッションとアイテムの状態整合性を自動検証

### Phase 3実装ファイル

**場所**: `features/photonest/application/local_import/use_case_phase3.py`

これは**参考実装**です。Phase 2が安定してから、段階的に移行してください。

### Phase 3の使い方

#### ステップ1: 状態管理サービスの初期化

```python
from features.photonest.infrastructure.local_import.repositories import (
    create_state_management_service,
)

# サービス作成
state_mgr, audit_logger = create_state_management_service(db.session)
```

#### ステップ2: セッションレベルの状態遷移

```python
# セッション開始
state_mgr.transition_session(
    session_id,
    SessionState.PROCESSING,
    reason="100個のファイルを処理開始",
)

# 処理中...

# セッション完了
state_mgr.transition_session(
    session_id,
    SessionState.IMPORTED,
    reason="処理完了: 95成功, 5失敗",
)
```

#### ステップ3: アイテムレベルの処理（with文）

```python
# 自動状態管理
with state_mgr.process_item(item_id, file_path, session_id) as ctx:
    # 自動的に PENDING → ANALYZING に遷移
    
    # ファイル解析
    analysis = analyze_file(file_path)
    
    # 明示的な状態遷移
    state_mgr.transition_item(ctx, ItemState.CHECKING, "重複チェック開始")
    
    if is_duplicate:
        # スキップ（自動的にSKIPPED状態へ）
        state_mgr.transition_item(ctx, ItemState.SKIPPED, "重複のためスキップ")
        return
    
    # ファイル移動
    state_mgr.transition_item(ctx, ItemState.MOVING, "ファイル移動開始")
    move_file(...)
    
    # DB更新
    state_mgr.transition_item(ctx, ItemState.UPDATING, "DB更新中")
    save_to_database(...)
    
    # 成功時は自動的に IMPORTED 状態へ遷移
    # エラー時は自動的に FAILED 状態へ遷移
```

### Phase 3の利点

| 項目 | Phase 2 | Phase 3 |
|------|---------|---------|
| **ログ記録** | 手動で各所に追加 | 自動記録 |
| **状態遷移** | 手動でステータス更新 | 自動遷移 |
| **エラー処理** | try/exceptを各所に記述 | with文で自動処理 |
| **整合性** | 手動チェック | 自動検証 |
| **コード量** | 多い | 少ない |
| **保守性** | 中 | 高 |

---

## 📈 段階的な移行計画

### フェーズ1: Phase 2の安定化（現在）

```
Week 1-2: Phase 2の本番デプロイ
  ✓ マイグレーション実行
  ✓ 監視とログ確認
  ✓ パフォーマンス影響の検証
  ✓ バグ修正
```

### フェーズ2: Phase 3の部分導入

```
Week 3-4: 新機能でPhase 3を試験導入
  □ 新しい処理フローをPhase 3で実装
  □ 既存処理はPhase 2のまま維持
  □ 並行稼働で動作確認
```

### フェーズ3: Phase 3への完全移行

```
Week 5-6: 既存処理をPhase 3に移行
  □ use_case.py を use_case_phase3.py に置き換え
  □ file_importer に with文を導入
  □ queue_processor に状態管理を統合
  □ 全体的なリファクタリング
```

---

## 🧪 テスト方法

### Phase 2のテスト

```python
# tests/test_local_import_phase2.py

def test_file_import_logs_to_audit_log(db_session):
    """ファイル取り込みが監査ログに記録される"""
    # ファイル取り込み実行
    result = file_importer.import_file(
        file_path="/test/image.jpg",
        import_dir="/import",
        originals_dir="/originals",
        session_id="test_session",
    )
    
    # 監査ログを確認
    logs = db_session.query(LocalImportAuditLog).filter_by(
        session_id="test_session"
    ).all()
    
    assert len(logs) > 0
    assert any(log.category == "file_operation" for log in logs)
    assert any(log.category == "duplicate_check" for log in logs)
    assert any(log.category == "performance" for log in logs)

def test_error_includes_recommended_actions(db_session):
    """エラー時に推奨アクションが記録される"""
    # エラーを発生させる
    with pytest.raises(Exception):
        file_importer.import_file(
            file_path="/nonexistent/file.jpg",
            import_dir="/import",
            originals_dir="/originals",
            session_id="test_session",
        )
    
    # エラーログを確認
    error_log = db_session.query(LocalImportAuditLog).filter_by(
        level="ERROR",
        session_id="test_session",
    ).first()
    
    assert error_log is not None
    assert error_log.recommended_actions is not None
    assert len(error_log.recommended_actions) > 0
```

### Phase 3のテスト

```python
# tests/test_local_import_phase3.py

def test_with_statement_auto_transitions(db_session):
    """with文により自動的に状態遷移する"""
    state_mgr, _ = create_state_management_service(db_session)
    
    with state_mgr.process_item("item_1", "/test/file.jpg", "session_1") as ctx:
        # ここで例外が発生してもFAILED状態に自動遷移
        assert ctx.current_state == ItemState.ANALYZING
    
    # with文を抜けると自動的にIMPORTED状態へ
    item_state = state_mgr.get_item_state("item_1")
    assert item_state == ItemState.IMPORTED

def test_error_auto_transitions_to_failed(db_session):
    """エラー時に自動的にFAILED状態へ遷移"""
    state_mgr, _ = create_state_management_service(db_session)
    
    with pytest.raises(Exception):
        with state_mgr.process_item("item_1", "/test/file.jpg", "session_1") as ctx:
            raise Exception("Test error")
    
    # エラー発生により自動的にFAILED状態へ
    item_state = state_mgr.get_item_state("item_1")
    assert item_state == ItemState.FAILED
```

---

## 📊 監視とメトリクス

### Phase 2で監視すべき指標

```sql
-- 1. エラー率
SELECT 
  DATE(timestamp) as date,
  COUNT(CASE WHEN level = 'ERROR' THEN 1 END) * 100.0 / COUNT(*) as error_rate
FROM local_import_audit_log
WHERE category IN ('file_operation', 'db_operation')
GROUP BY DATE(timestamp)
ORDER BY date DESC;

-- 2. 平均処理時間
SELECT 
  category,
  AVG(duration_ms) as avg_duration_ms,
  PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95_duration_ms
FROM local_import_audit_log
WHERE category = 'performance'
GROUP BY category;

-- 3. 重複率
SELECT 
  COUNT(CASE WHEN details->>'is_duplicate' = 'true' THEN 1 END) * 100.0 / COUNT(*) as duplicate_rate
FROM local_import_audit_log
WHERE category = 'duplicate_check';

-- 4. 推奨アクションの頻度
SELECT 
  error_type,
  recommended_actions,
  COUNT(*) as frequency
FROM local_import_audit_log
WHERE level = 'ERROR'
  AND recommended_actions IS NOT NULL
GROUP BY error_type, recommended_actions
ORDER BY frequency DESC;
```

### Phase 3で監視すべき指標

```sql
-- 1. 状態遷移の正常性
SELECT 
  from_state,
  to_state,
  COUNT(*) as transition_count,
  AVG(duration_ms) as avg_duration
FROM local_import_audit_log
WHERE category = 'state_transition'
GROUP BY from_state, to_state
ORDER BY transition_count DESC;

-- 2. 整合性チェック結果
SELECT 
  DATE(timestamp) as date,
  COUNT(CASE WHEN details->>'is_consistent' = 'false' THEN 1 END) as inconsistency_count
FROM local_import_audit_log
WHERE category = 'consistency'
GROUP BY DATE(timestamp);
```

---

## 🎯 成功の指標

### Phase 2成功の条件

- ✅ エラー率が1%未満
- ✅ パフォーマンス劣化が5%未満
- ✅ すべての処理に監査ログが記録される
- ✅ 推奨アクションによりエラー解決率が向上
- ✅ APIからログデータを正常に取得できる

### Phase 3成功の条件

- ✅ 状態不整合が0件
- ✅ with文によるコード量が50%削減
- ✅ エラーハンドリング漏れが0件
- ✅ 自動状態遷移が100%正確
- ✅ パフォーマンスがPhase 2と同等以上

---

## 📚 参考資料

### 実装ファイル

| ファイル | 説明 | Phase |
|---------|------|-------|
| [use_case.py](../features/photonest/application/local_import/use_case.py) | Phase 2統合済み | 2 |
| [file_importer.py](../features/photonest/application/local_import/file_importer.py) | Phase 2統合済み | 2 |
| [use_case_phase3.py](../features/photonest/application/local_import/use_case_phase3.py) | Phase 3参考実装 | 3 |
| [integration_example.py](../features/photonest/application/local_import/integration_example.py) | 統合サンプル | 2/3 |

### ドキュメント

- [デプロイガイド](./local_import_state_management_deployment.md)
- [実行手順](./RUN_MIGRATION.md)
- [次のステップ](./NEXT_STEPS.md)

---

## 💡 トラブルシューティング

### Phase 2の問題

**問題**: ログが記録されない

**解決策**:
```python
# 監査ロガーが初期化されているか確認
from features.photonest.infrastructure.local_import.logging_integration import get_audit_logger
logger = get_audit_logger()
print(f"Audit logger initialized: {logger is not None}")
```

**問題**: パフォーマンスが劣化した

**解決策**:
```sql
-- 遅い処理を特定
SELECT item_id, duration_ms, message
FROM local_import_audit_log
WHERE category = 'performance'
  AND duration_ms > 10000  -- 10秒以上
ORDER BY duration_ms DESC
LIMIT 10;
```

### Phase 3の問題

**問題**: 状態遷移が失敗する

**解決策**:
```python
# 状態機械のバリデーションを確認
from features.photonest.domain.local_import.state_machine import (
    SessionStateMachine,
    StateMachineError,
)

try:
    machine = SessionStateMachine()
    machine.can_transition(current_state, new_state)
except StateMachineError as e:
    print(f"Invalid transition: {e}")
```

---

これでPhase 2とPhase 3の完全な統合ガイドが完成しました！
