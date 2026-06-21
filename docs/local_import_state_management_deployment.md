# Local Import状態管理システム - デプロイガイド

## 📋 概要

このガイドでは、Local Import状態管理システムを本番環境にデプロイする手順を説明します。

## ✅ 実装済みコンポーネント

### Backend (Python/Flask)
- ✅ Domain層: State Machine (SessionState, ItemState)
- ✅ Application層: State Synchronizer, State Management Service, Troubleshooting Engine
- ✅ Infrastructure層: Audit Logger, Repositories, Logging Integration
- ✅ Presentation層: REST API (8エンドポイント)

### Frontend (Vue.js)
- ✅ LocalImportStatus.vue: 状態監視UI
  - エラー一覧タブ
  - 状態遷移タブ
  - パフォーマンスタブ
  - トラブルシューティングタブ
  - 整合性チェック機能

### Database
- ✅ Alembic Migration: local_import_audit_log テーブル
- ✅ MariaDB互換設計

### Integration
- ✅ Phase 1: ログのみ追加（既存コード非侵襲）
- ⏳ Phase 2: 状態遷移追加（要実装）
- ⏳ Phase 3: 完全統合（要実装）

---

## 🚀 デプロイ手順

### ステップ 1: コード変更の確認

✅ **完了済み**

以下のファイルが変更されています：

```
webapp/__init__.py
  - Local Import状態管理APIのblueprint登録
  - 監査ロガー初期化処理追加

migrations/versions/a1b2c3d4e5f6_add_local_import_audit_log.py
  - 新規作成（監査ログテーブル）
```

### ステップ 2: マイグレーションの準備

**重要**: マイグレーションファイルの `down_revision` を最新のrevisionに置き換えてください。

```powershell
# 現在の最新マイグレーションを確認
flask db current

# migrations/versions/a1b2c3d4e5f6_add_local_import_audit_log.py を編集
# down_revision = None  # ← これを最新のrevision IDに変更
```

**例**:
```python
# 修正前
down_revision = None

# 修正後（例）
down_revision = 'cc5f8f58c7d4'  # 実際の最新revision IDに置き換える
```

### ステップ 3: データベースマイグレーション実行

```powershell
# マイグレーション実行
flask db upgrade

# 確認: テーブルが作成されたか確認
flask db current
```

**期待される結果**:
- `local_import_audit_log` テーブルが作成される
- 10個のインデックスが作成される

**ロールバック手順**（問題発生時）:
```powershell
flask db downgrade -1
```

### ステップ 4: アプリケーション再起動

```powershell
# 開発環境
python main.py

# 本番環境（Gunicorn等）
systemctl restart photonest-web
```

**確認ポイント**:
- ログに「Local Import監査ロガーを初期化しました」が出力される
- エラーが発生していないこと

### ステップ 5: API動作確認

```powershell
# ヘルスチェック
curl http://localhost:5000/health

# API Docs確認
# ブラウザで http://localhost:5000/api/docs を開く
# "local_import_status" セクションが表示されることを確認
```

**確認するエンドポイント**:
- GET `/api/local-import/sessions/<id>/status`
- GET `/api/local-import/sessions/<id>/errors`
- GET `/api/local-import/sessions/<id>/transitions`
- GET `/api/local-import/sessions/<id>/consistency-check`
- GET `/api/local-import/sessions/<id>/troubleshooting`
- GET `/api/local-import/sessions/<id>/performance`
- GET `/api/local-import/sessions/<id>/logs`
- GET `/api/local-import/items/<id>/logs`

### ステップ 6: Vue UIの統合（オプション）

**方法1: 既存ページに埋め込む**

```vue
<!-- 例: webapp/src/views/LocalImportDashboard.vue -->
<template>
  <div>
    <h1>Local Import ダッシュボード</h1>
    <LocalImportStatus :sessionId="currentSessionId" />
  </div>
</template>

<script>
import LocalImportStatus from '@/components/LocalImportStatus.vue';

export default {
  components: {
    LocalImportStatus,
  },
  data() {
    return {
      currentSessionId: 1, // 実際のセッションIDを渡す
    };
  },
};
</script>
```

**方法2: 新規ルート作成**

```javascript
// webapp/src/router/index.js
import LocalImportStatus from '@/components/LocalImportStatus.vue';

const routes = [
  // 既存のルート...
  {
    path: '/local-import/:sessionId/status',
    name: 'LocalImportStatus',
    component: LocalImportStatus,
    props: (route) => ({ sessionId: Number(route.params.sessionId) }),
  },
];
```

---

## 📊 Phase 2: 状態遷移の統合

Phase 1（ログのみ）が安定したら、Phase 2で状態遷移を追加します。

### 対象ファイル
- `core/tasks/local_import.py`（または該当するタスクファイル）

### 変更例

```python
# 既存コード
def process_file(file_path, session_id):
    # ファイル処理...
    pass

# Phase 2統合後
from features.photonest.infrastructure.local_import.logging_integration import (
    log_with_audit,
    log_file_operation,
    log_performance,
)

def process_file(file_path, session_id):
    item_id = generate_item_id(file_path)
    
    log_with_audit("ファイル処理開始", session_id=session_id, item_id=item_id)
    
    # ファイル処理...
    log_file_operation(
        "ファイル移動完了",
        file_path=new_path,
        operation="move",
        session_id=session_id,
        item_id=item_id,
    )
    
    log_with_audit("ファイル処理完了", session_id=session_id, item_id=item_id)
```

---

## 🔍 Phase 3: 完全統合（with文）

Phase 2が安定したら、Phase 3でcontext managerを使った完全統合を行います。

### 変更例

```python
from features.photonest.infrastructure.local_import.repositories import (
    create_state_management_service,
)

def process_file(file_path, session_id):
    item_id = generate_item_id(file_path)
    state_mgr, _ = create_state_management_service(db.session)
    
    # with文で自動的に状態遷移
    with state_mgr.process_item(item_id, file_path, session_id) as ctx:
        # 処理...
        # エラー時は自動的にFAILED状態に遷移
        # 成功時は自動的にIMPORTED状態に遷移
        pass
```

---

## 🧪 テスト手順

### 1. ユニットテスト実行

```powershell
pytest tests/test_local_import_state_management.py -v
```

### 2. インポート検証

```powershell
python tests/test_import_validation.py
```

### 3. API手動テスト

```powershell
# セッション状態取得
curl http://localhost:5000/api/local-import/sessions/1/status

# エラーログ取得
curl http://localhost:5000/api/local-import/sessions/1/errors

# トラブルシューティングレポート
curl http://localhost:5000/api/local-import/sessions/1/troubleshooting
```

### 4. UI動作確認

1. ブラウザで `/local-import/<session_id>/status` を開く
2. 各タブが正しく表示されることを確認
3. 自動リフレッシュ（30秒）が動作することを確認
4. 整合性チェックボタンをクリックしてモーダルが表示されることを確認

---

## ⚠️ トラブルシューティング

### 問題1: マイグレーションエラー

**症状**:
```
alembic.util.exc.CommandError: Can't locate revision identified by 'None'
```

**原因**: `down_revision = None` が修正されていない

**対処**:
1. `migrations/versions/a1b2c3d4e5f6_add_local_import_audit_log.py` を開く
2. `down_revision = None` を最新のrevision IDに変更
3. `flask db upgrade` を再実行

### 問題2: 監査ロガー初期化失敗

**症状**:
```
WARNING: Local Import監査ロガー初期化をスキップしました: ...
```

**原因**: DBテーブルが存在しない

**対処**:
1. `flask db current` でマイグレーション状態確認
2. `flask db upgrade` でマイグレーション実行
3. アプリ再起動

### 問題3: API 404エラー

**症状**: `/api/local-import/sessions/<id>/status` が404

**原因**: Blueprint未登録

**対処**:
1. `webapp/__init__.py` で `app.register_blueprint(local_import_status_bp)` が追加されているか確認
2. アプリ再起動
3. `/api/docs` で "local_import_status" セクションが表示されるか確認

### 問題4: Vue componentエラー

**症状**: `Cannot find module '@/components/LocalImportStatus.vue'`

**原因**: ファイルパスが間違っている

**対処**:
1. ファイルが `webapp/src/components/LocalImportStatus.vue` に存在するか確認
2. import文のパスを確認
3. Vite/Webpack開発サーバー再起動

---

## 📈 モニタリング

### ログ確認

```sql
-- 最近のエラーログ
SELECT * FROM local_import_audit_log 
WHERE level = 'ERROR' 
ORDER BY timestamp DESC 
LIMIT 10;

-- セッション別の処理状況
SELECT session_id, category, COUNT(*) 
FROM local_import_audit_log 
WHERE session_id = 1 
GROUP BY category;

-- パフォーマンス統計
SELECT 
  category,
  COUNT(*) as count,
  AVG(duration_ms) as avg_duration,
  MAX(duration_ms) as max_duration
FROM local_import_audit_log 
WHERE duration_ms IS NOT NULL 
GROUP BY category;
```

### メトリクス

- **エラー率**: エラーログ数 / 総ログ数
- **平均処理時間**: AVG(duration_ms)
- **状態遷移数**: COUNT(category='state_transition')
- **整合性チェック**: is_consistent = TRUE の割合

---

## 🔒 セキュリティ考慮事項

1. **API認証**: すべてのエンドポイントに適切な認証を追加することを推奨
2. **ログの機密情報**: ファイルパス、ユーザーIDなどがログに含まれるため、アクセス制御を確認
3. **DB権限**: `local_import_audit_log` へのアクセス権限を適切に設定

---

## 📝 ロールバック手順

問題が発生した場合の緊急ロールバック手順：

```powershell
# 1. マイグレーションを戻す
flask db downgrade -1

# 2. コードを元に戻す
git revert <commit-hash>

# 3. アプリ再起動
systemctl restart photonest-web
```

**注意**: ロールバック時、`local_import_audit_log` テーブルのデータは失われます。必要に応じてバックアップを取得してください。

---

## ✅ デプロイ完了チェックリスト

- [ ] マイグレーション `down_revision` を修正
- [ ] `flask db upgrade` 実行成功
- [ ] アプリケーション起動成功
- [ ] ログに「監査ロガーを初期化しました」が出力
- [ ] `/api/docs` で新しいエンドポイントが表示
- [ ] API手動テスト成功（最低1エンドポイント）
- [ ] Vue componentが正しく表示（オプション）
- [ ] ユニットテスト実行成功
- [ ] 既存機能に影響がないことを確認

---

## 📞 サポート

問題が発生した場合は、以下の情報と共に報告してください：

1. エラーメッセージ全文
2. 実行したコマンド
3. `flask db current` の出力
4. アプリケーションログ（直近100行）
5. `SELECT COUNT(*) FROM local_import_audit_log` の結果

---

## 次のステップ

1. ✅ **Phase 1デプロイ完了** → このガイドの手順を実行
2. ⏳ **Phase 2実装** → 既存コードに状態遷移を追加
3. ⏳ **Phase 3実装** → context managerによる完全統合
4. ⏳ **モニタリング強化** → Grafana等でダッシュボード作成
5. ⏳ **アラート設定** → エラー率が閾値を超えたら通知
