# Local Import 状態管理・トラブルシューティングシステム

**作成日**: 2025-12-28

## 概要

Local Importの処理において、**状態の不整合を防ぎ、問題が発生した際に即座に原因と対処法を把握できる**ようにする包括的な状態管理・監査システムです。

### 主要機能

1. **状態遷移管理**: 不正な状態遷移を防止
2. **自動同期**: セッション状態とアイテム状態の整合性を保証
3. **構造化ログ**: すべての操作をDB保存し、完全なトレーサビリティを実現
4. **自動診断**: エラーを分析し、推奨アクションを自動提示
5. **整合性チェック**: 状態の不一致を検出し、修正方法を提案

---

## アーキテクチャ

### レイヤー構成

```
┌─────────────────────────────────────────────────────────────┐
│  Presentation層（API/UI）                                     │
│  - 状態表示、エラーメッセージ、推奨アクション表示              │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  Application層                                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ StateManagementService                                 │  │
│  │  - 状態遷移の制御                                      │  │
│  │  - コンテキスト管理                                    │  │
│  │  - パフォーマンス計測                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ StateSynchronizer                                      │  │
│  │  - セッション/アイテム状態の同期                       │  │
│  │  - 整合性検証                                          │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ TroubleshootingEngine                                  │  │
│  │  - エラー診断                                          │  │
│  │  - 推奨アクション生成                                  │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  Domain層                                                     │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ SessionStateMachine / ItemStateMachine                 │  │
│  │  - 状態遷移ルールの定義                                │  │
│  │  - 不正遷移の防止                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ StateConsistencyValidator                              │  │
│  │  - 整合性検証ロジック                                  │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────┬────────────────────────────────────────┘
                     │
┌────────────────────▼────────────────────────────────────────┐
│  Infrastructure層                                             │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ AuditLogger / AuditLogRepository                       │  │
│  │  - 構造化ログのDB保存                                  │  │
│  │  - ログ検索・集計                                      │  │
│  └──────────────────────────────────────────────────────┘  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ SessionRepository / ItemRepository                     │  │
│  │  - 状態の永続化                                        │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```


```
┌─────────────────────────────────────────────────────┐
│                   Frontend (Vue.js)                  │
│        LocalImportStatus.vue (4タブUI)              │
└──────────────────┬──────────────────────────────────┘
                   │ HTTP REST API
┌──────────────────▼──────────────────────────────────┐
│            Presentation Layer (Flask)                │
│   local_import_status_api.py (8エンドポイント)      │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│            Application Layer                         │
│  ├─ State Management Service                        │
│  ├─ State Synchronizer                              │
│  └─ Troubleshooting Engine                          │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│            Domain Layer                              │
│  ├─ SessionStateMachine (10状態)                    │
│  ├─ ItemStateMachine (10状態)                       │
│  └─ StateConsistencyValidator                       │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│         Infrastructure Layer                         │
│  ├─ AuditLogger (構造化ログ)                        │
│  ├─ Repositories (DB操作)                           │
│  └─ Logging Integration (Phase 1)                   │
└──────────────────┬──────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────┐
│              Database (MariaDB)                      │
│  ├─ picker_session (既存)                           │
│  └─ local_import_audit_log (新規)                   │
└─────────────────────────────────────────────────────┘
```

---

## 状態遷移モデル

### セッション状態

```
PENDING (初期状態)
  ↓
READY (ファイル選択完了)
  ↓
EXPANDING (ディレクトリ展開中)
  ↓
PROCESSING (処理中)
  ↓
ENQUEUED (ワーカーキューに投入)
  ↓
IMPORTING (インポート実行中)
  ↓
IMPORTED (完了)

※ どの段階からも → CANCELED / ERROR / FAILED に遷移可能
※ FAILED → PROCESSING への再試行も可能
```

### アイテム状態

```
PENDING (待機中)
  ↓
ANALYZING (ファイル解析中)
  ↓
CHECKING (重複チェック中)
  ↓
MOVING (ファイル移動中)
  ↓
UPDATING (DB更新中)
  ↓
IMPORTED (完了)

※ 各段階から → FAILED / SKIPPED / MISSING に遷移可能
※ FAILED → ANALYZING への再試行も可能
```

### 整合性ルール

1. **セッションIMPORTED** → 全アイテムが終了状態
2. **セッション処理中** → 少なくとも1つのアイテムが処理中または未処理
3. **セッションFAILED** → 失敗率が50%以上
4. **アイテムがゼロ** → セッションはPENDINGまたはREADY

---

## 使用方法

### 1. 基本的な使用パターン

```python
from features.photonest.application.local_import.state_management_service import (
    StateManagementService,
)
from features.photonest.domain.local_import.state_machine import ItemState

# サービスを初期化
state_mgr = StateManagementService(state_synchronizer, audit_logger)

# アイテム処理
with state_mgr.process_item(item_id, file_path, session_id) as ctx:
    # 自動的に PENDING → ANALYZING に遷移
    
    # ファイル解析
    ctx.structured_logger.info("ファイル解析開始", file_size=1024000)
    result = analyze_file(file_path)
    
    # 重複チェック開始
    state_mgr.transition_item(ctx, ItemState.CHECKING, "重複チェック開始")
    duplicate = check_duplicate(result)
    
    if duplicate:
        # スキップ
        state_mgr.transition_item(ctx, ItemState.SKIPPED, "重複のためスキップ")
        return
    
    # ファイル移動
    state_mgr.transition_item(ctx, ItemState.MOVING, "ファイル移動開始")
    move_file(file_path, destination)
    
    # DB更新
    state_mgr.transition_item(ctx, ItemState.UPDATING, "DB更新開始")
    save_to_db(result)
    
    # 自動的に IMPORTED に遷移してコミット
```

### 2. エラーハンドリング

```python
from features.photonest.application.local_import.troubleshooting import (
    TroubleshootingEngine,
)

engine = TroubleshootingEngine()

try:
    process_file(file_path)
except Exception as e:
    # エラーを診断
    result = engine.diagnose(e, {"file_path": file_path, "operation": "移動"})
    
    # ユーザーに表示
    print(f"エラー: {result.summary}")
    print(f"診断: {result.diagnosis}")
    print("推奨アクション:")
    for action in result.recommended_actions:
        print(f"  - {action}")
    
    # ログに記録（自動的に推奨アクションも保存される）
    ctx.structured_logger.error(
        result.summary,
        exception=e,
        recommended_actions=result.recommended_actions,
    )
```

### 3. 整合性チェック

```python
# 定期的に実行（例: 処理完了後、夜間バッチ）
result = state_mgr.validate_consistency(session_id)

if not result["is_consistent"]:
    print("⚠️ 状態の不整合を検出:")
    for issue in result["issues"]:
        print(f"  - {issue}")
    
    print("\n推奨対応:")
    for action in result["recommendations"]:
        print(f"  - {action}")
```

### 4. 状態の同期

```python
# セッション状態をアイテム状態に基づいて自動更新
snapshot = state_mgr.get_session_snapshot(session_id)

print(f"セッション状態: {snapshot.state.value}")
print(f"全アイテム数: {snapshot.item_count}")
print(f"成功: {snapshot.success_count}")
print(f"失敗: {snapshot.failed_count}")
print(f"処理中: {snapshot.processing_count}")
```

---

## 監査ログ

### ログの種類

| カテゴリ | 用途 | 記録内容 |
|---------|------|----------|
| `state_transition` | 状態遷移 | from_state, to_state, reason |
| `file_operation` | ファイル操作 | file_path, operation, duration |
| `db_operation` | DB操作 | entity_type, operation, query |
| `validation` | バリデーション | validation_type, result |
| `duplicate_check` | 重複チェック | hash, match_type, result |
| `error` | エラー | error_type, stack_trace, actions |
| `performance` | パフォーマンス | duration_ms, throughput |
| `consistency` | 整合性チェック | issues, recommendations |

### ログの検索

```python
from features.photonest.infrastructure.local_import.audit_log_repository import (
    AuditLogRepository,
    LogLevel,
    LogCategory,
)

repo = AuditLogRepository(db_session)

# セッションのエラーログを取得
errors = repo.get_errors(session_id=123)
for log in errors:
    print(f"{log.timestamp}: {log.message}")
    if log.recommended_actions:
        print("  推奨アクション:", log.recommended_actions)

# 状態遷移履歴を取得
transitions = repo.get_state_transitions(session_id=123)
for log in transitions:
    print(f"{log.from_state} → {log.to_state}: {log.details.get('reason')}")

# パフォーマンスメトリクスを取得
metrics = repo.get_performance_metrics(session_id=123)
total_duration = sum(log.duration_ms for log in metrics)
print(f"総処理時間: {total_duration/1000:.2f}秒")
```

---

## トラブルシューティング

### よくあるエラーと対処法

#### 1. ファイルが見つからない (FileNotFoundError)

**症状**:
```
エラー: ファイル処理失敗: /path/to/file.jpg
診断: ファイルパス '/path/to/file.jpg' が存在しないか、アクセスできません
```

**推奨アクション**:
1. ファイルの存在を確認: `ls -la /path/to/file.jpg`
2. ファイルが移動・削除されていないか確認
3. パスの表記が正しいか確認（相対パス/絶対パス）
4. ディレクトリの権限を確認
5. 別の場所にファイルがないか検索

**根本原因**:
- ファイルが処理前に削除された
- パスが間違っている
- マウントポイントがアンマウントされた

---

#### 2. 権限エラー (PermissionError)

**症状**:
```
エラー: ファイル移動失敗: アクセス権限がありません
診断: ファイルまたはディレクトリへの読み書き権限がありません
```

**推奨アクション**:
1. ファイルの所有者とパーミッションを確認: `ls -la /path/to/file.jpg`
2. 実行ユーザーの権限を確認: `id`
3. chmod/chownでパーミッションを修正:
   ```bash
   sudo chown app_user:app_group /path/to/file.jpg
   sudo chmod 644 /path/to/file.jpg
   ```
4. 他のプロセスがファイルをロックしていないか確認: `lsof /path/to/file.jpg`

**根本原因**:
- アプリケーションユーザーが異なる
- パーミッションが正しく設定されていない
- SELinux/AppArmorによる制限

---

#### 3. 状態の不整合

**症状**:
```
⚠️ 状態の不整合を検出:
  - セッションIMPORTED状態なのに未完了アイテムあり: ['item_123', 'item_456']
```

**推奨アクション**:
1. 未完了アイテムを個別に処理
2. またはセッション状態をPROCESSINGに戻す:
   ```python
   state_mgr.transition_session(
       session_id,
       SessionState.PROCESSING,
       "未完了アイテムがあるため再処理"
   )
   ```

**根本原因**:
- 処理中にエラーが発生し、状態更新がスキップされた
- 手動でDBを更新した
- 並行処理での競合

---

#### 4. ディスク容量不足 (OSError: No space left on device)

**症状**:
```
エラー: ファイル移動失敗: ディスク容量不足の可能性
```

**推奨アクション**:
1. ディスク容量を確認:
   ```bash
   df -h
   ```
2. 不要なファイルを削除:
   ```bash
   # 一時ファイル
   sudo rm -rf /tmp/*
   
   # 古いログ
   sudo find /var/log -name "*.log" -mtime +30 -delete
   ```
3. iノード使用率を確認:
   ```bash
   df -i
   ```

**根本原因**:
- ディスク容量が不足
- iノードが枯渇
- 大量の小ファイル

---

### トラブルシューティングレポート生成

```python
from features.photonest.application.local_import.troubleshooting import (
    generate_troubleshooting_report,
)

# エラーログと統計を取得
errors = repo.get_errors(session_id=123)
stats = repo.get_session_stats(session_id=123)

# レポート生成
report = generate_troubleshooting_report(
    session_id=123,
    session_state="failed",
    errors=[log.to_dict() for log in errors],
    stats=stats,
)

print(f"深刻度: {report['severity']}")
print(f"総エラー数: {report['total_errors']}")
print(f"最多エラー: {report['top_error_category']}")
print("\n推奨アクション:")
for action in report['recommended_actions']:
    print(f"  - {action}")
```

---

## パフォーマンスモニタリング

### 計測対象

1. **ファイル処理時間**: 解析 → 重複チェック → 移動 → DB更新
2. **スループット**: MB/秒
3. **状態遷移の頻度**: 遷移あたりの平均時間
4. **エラー率**: エラー発生頻度

### モニタリング例

```python
from features.photonest.application.local_import.state_management_service import (
    PerformanceTracker,
)

tracker = PerformanceTracker(structured_logger)

# 操作時間を計測
with tracker.measure("duplicate_check", file_size_bytes=1024000):
    result = check_duplicate(file_hash)

# ログに自動記録される:
# {
#   "operation_name": "duplicate_check",
#   "duration_ms": 150.5,
#   "file_size_bytes": 1024000,
#   "throughput_mbps": 6.5
# }
```

---

## API統合

### エンドポイント例

```python
from flask import Blueprint
from features.photonest.application.local_import.state_management_service import (
    StateManagementService,
)

bp = Blueprint("local_import_status", __name__, url_prefix="/api/local-import")

@bp.get("/sessions/<int:session_id>/status")
def get_session_status(session_id: int):
    """セッション状態を取得"""
    snapshot = state_mgr.get_session_snapshot(session_id)
    
    return {
        "session_id": session_id,
        "state": snapshot.state.value,
        "stats": {
            "total": snapshot.item_count,
            "success": snapshot.success_count,
            "failed": snapshot.failed_count,
            "processing": snapshot.processing_count,
        },
        "last_updated": snapshot.last_updated.isoformat(),
    }

@bp.get("/sessions/<int:session_id>/consistency-check")
def check_consistency(session_id: int):
    """整合性をチェック"""
    result = state_mgr.validate_consistency(session_id)
    
    return result

@bp.get("/sessions/<int:session_id>/errors")
def get_errors(session_id: int):
    """エラーログを取得"""
    errors = repo.get_errors(session_id=session_id, limit=50)
    
    return {
        "errors": [
            {
                "timestamp": log.timestamp.isoformat(),
                "message": log.message,
                "error_type": log.error_type,
                "recommended_actions": log.recommended_actions,
            }
            for log in errors
        ]
    }

@bp.get("/sessions/<int:session_id>/troubleshooting")
def get_troubleshooting_report(session_id: int):
    """トラブルシューティングレポートを取得"""
    errors = repo.get_errors(session_id=session_id)
    stats = repo.get_session_stats(session_id)
    session_state = repo.get_session_state(session_id)
    
    report = generate_troubleshooting_report(
        session_id,
        session_state.value,
        [log.to_dict() for log in errors],
        stats,
    )
    
    return report
```

---

## デプロイ手順

### 1. マイグレーション実行

```bash
# 仮想環境をアクティベート
source /home/kyon/myproject/.venv/bin/activate

# マイグレーション実行
flask db upgrade
```

### 2. 既存データの移行（必要に応じて）

```python
# 既存のセッションに対して初期ログを作成
from features.photonest.infrastructure.local_import.audit_log_repository import (
    AuditLogRepository,
)

repo = AuditLogRepository(db.session)

for session in PickerSession.query.all():
    entry = AuditLogEntry(
        level=LogLevel.INFO,
        category=LogCategory.STATE_TRANSITION,
        message=f"セッション作成: 既存データからの移行",
        session_id=session.id,
    )
    repo.save(entry)

db.session.commit()
```

### 3. 既存コードの更新

`core/tasks/local_import.py` を段階的に更新:

```python
# Before
def process_file(file_path):
    # 直接処理...
    pass

# After
def process_file(file_path, session_id, item_id):
    with state_mgr.process_item(item_id, file_path, session_id) as ctx:
        # 処理...
        pass
```

---

## まとめ

### 実現したこと

✅ **状態の一元管理**: 不正な遷移を完全に防止  
✅ **自動同期**: セッション/アイテム状態の整合性を常に保証  
✅ **完全なトレーサビリティ**: すべての操作をDB保存  
✅ **自動診断**: エラーを分析し、推奨アクションを即座に提示  
✅ **簡単なトラブルシューティング**: 何が問題で、何をすべきかが一目瞭然

### 効果

- 🔍 **デバッグ時間の大幅削減**: ログから即座に原因特定
- 🛡️ **状態不整合の根絶**: 状態遷移機械が不正遷移を防止
- 📊 **運用の可視化**: リアルタイムで処理状況を把握
- 🚀 **品質向上**: 構造化ログによる継続的な改善

### 次のステップ

1. [ ] UIに状態表示とエラー詳細を追加
2. [ ] アラート機能（エラー率が閾値を超えたら通知）
3. [ ] パフォーマンスダッシュボード
4. [ ] 自動リトライ機能

---

**参照ドキュメント**:
- [local_import_refactoring.md](local_import_refactoring.md) - DDD設計
- [local_import_integration_guide.md](local_import_integration_guide.md) - 統合ガイド
- [AGENTS.md](../AGENTS.md) - プロジェクト規約
