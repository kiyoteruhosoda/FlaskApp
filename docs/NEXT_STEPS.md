# Local Import状態管理システム - 次のステップ実行ガイド

## ✅ 完了した作業

1. **マイグレーションファイルの修正完了**
   - `down_revision` を `'a4e3d9f2c5ab'` に設定
   - マイグレーション準備完了

2. **統合コード完了**
   - Flask blueprint登録済み
   - 監査ロガー初期化処理追加済み

---

## 🚀 次に実行すべきコマンド

### Windows環境での実行方法

```powershell
# 方法1: Dockerコンテナ内で実行（推奨）
docker-compose exec web flask db upgrade

# 方法2: Pythonが利用可能な場合
python -m flask db upgrade

# 方法3: pyコマンドが利用可能な場合  
py -m flask db upgrade
```

### Linux/WSL環境での実行方法

```bash
# 仮想環境をアクティベート
source /home/kyon/myproject/.venv/bin/activate

# マイグレーション実行
flask db upgrade

# アプリケーション起動
python main.py
```

---

## 📋 実行前の確認事項

### 1. 環境変数の確認
```powershell
# .env ファイルが存在するか確認
Get-Content .env.example

# データベース接続情報を確認
# SQLALCHEMY_DATABASE_URI が正しく設定されているか
```

### 2. データベースの状態確認
```sql
-- 現在のマイグレーション状態を確認（SQLクライアントから）
SELECT * FROM alembic_version;

-- picker_sessionテーブルが存在することを確認
SHOW TABLES LIKE 'picker_session';
```

### 3. バックアップ推奨
```powershell
# 本番環境の場合、DBバックアップを取得
# mysqldump -u user -p database_name > backup_$(Get-Date -Format 'yyyyMMdd_HHmmss').sql
```

---

## ⚡ 簡略化された実行手順

### Docker環境を使用している場合（最も簡単）

```powershell
# 1. コンテナが起動しているか確認
docker-compose ps

# 2. マイグレーション実行
docker-compose exec web flask db upgrade

# 3. アプリケーション再起動
docker-compose restart web

# 4. 確認
docker-compose logs web | Select-String "監査ロガー"
```

### 結果の確認

```powershell
# APIドキュメントで新しいエンドポイントを確認
# ブラウザで http://localhost:5000/api/docs を開く

# または curlでテスト
curl http://localhost:5000/api/local-import/sessions/1/status
```

---

## 🐛 トラブルシューティング

### エラー: "flask command not found"

**原因**: Python環境が正しく設定されていない

**解決策**:
```powershell
# Docker環境を使用
docker-compose exec web flask db upgrade

# または、Pythonモジュールとして実行
python -m flask db upgrade
```

### エラー: "Can't locate revision identified by 'a4e3d9f2c5ab'"

**原因**: 指定したdown_revisionが存在しない

**解決策**:
```powershell
# 現在のマイグレーション履歴を確認
docker-compose exec web flask db history

# 最新のrevisionを確認して、マイグレーションファイルを修正
```

### エラー: "Table 'local_import_audit_log' already exists"

**原因**: テーブルが既に作成されている

**解決策**:
```powershell
# マイグレーション履歴を確認
docker-compose exec web flask db current

# 必要に応じてマイグレーションをスキップ
docker-compose exec web flask db stamp a1b2c3d4e5f6
```

---

## 📊 実行後の検証

### 1. テーブル作成の確認
```sql
-- local_import_audit_logテーブルが作成されたか確認
DESCRIBE local_import_audit_log;

-- インデックスが作成されたか確認
SHOW INDEX FROM local_import_audit_log;
```

### 2. API動作確認
```powershell
# セッション状態APIテスト
curl http://localhost:5000/api/local-import/sessions/1/status

# Swagger UIで確認
# http://localhost:5000/api/docs
# "local_import_status" セクションを探す
```

### 3. ログ確認
```powershell
# アプリケーションログを確認
docker-compose logs web | Select-String "監査ロガー"

# "Local Import監査ロガーを初期化しました" が出力されていればOK
```

### 4. データベースログ確認
```sql
-- 監査ログが記録されているか確認
SELECT COUNT(*) FROM local_import_audit_log;

-- 最新のログを確認
SELECT * FROM local_import_audit_log ORDER BY timestamp DESC LIMIT 5;
```

---

## 🎯 成功の指標

以下がすべて確認できれば、デプロイ成功です：

- ✅ マイグレーション実行がエラーなく完了
- ✅ `local_import_audit_log` テーブルが作成された
- ✅ 10個のインデックスが作成された
- ✅ アプリケーション起動時に「監査ロガーを初期化しました」が出力
- ✅ `/api/docs` に "local_import_status" セクションが表示
- ✅ API呼び出しが正常に動作（404エラーなし）

---

## 📞 次のアクション

### 即座に実行
```powershell
docker-compose exec web flask db upgrade
```

### 確認
```powershell
# ログ確認
docker-compose logs web --tail 50

# API確認
curl http://localhost:5000/api/docs
```

### Phase 2への移行
- [integration_example.py](../features/photonest/application/local_import/integration_example.py) を参照
- 既存のlocal_import処理に `log_with_audit()` を追加

---

これで完全に動作する状態管理システムが稼働します！🚀
