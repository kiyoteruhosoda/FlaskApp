# 📋 実行コマンド - クイックリファレンス

## 🎯 今すぐ実行すべきコマンド

### ✅ ステップ1: マイグレーションファイルの準備（完了済み）
```
down_revision を 'a4e3d9f2c5ab' に設定済み
```

### 🚀 ステップ2: マイグレーション実行

#### 推奨方法: Docker Compose（本番環境と同じ）

```powershell
# まずDocker Composeが利用可能か確認
docker compose version

# コンテナが起動しているか確認
docker compose ps

# マイグレーション実行
docker compose exec web flask db upgrade

# 結果確認
docker compose exec web flask db current
```

#### 代替方法: ローカルPython環境

**Windows PowerShell:**
```powershell
# 環境変数を設定（.envファイルから読み込み）
$env:FLASK_APP = "main.py"

# マイグレーション実行
py -m flask db upgrade

# または
python -m flask db upgrade
```

**WSL/Linux:**
```bash
# 仮想環境アクティベート（存在する場合）
source .venv/bin/activate

# または特定のパス
source /home/kyon/myproject/.venv/bin/activate

# マイグレーション実行
flask db upgrade
```

---

## ✅ 実行後の確認コマンド

### 1. マイグレーション成功確認
```powershell
# Docker
docker compose exec web flask db current

# ローカル
flask db current

# 期待される出力: a1b2c3d4e5f6 (rev) が含まれる
```

### 2. テーブル作成確認（SQLクライアントで）
```sql
-- テーブルの存在確認
SHOW TABLES LIKE 'local_import_audit_log';

-- テーブル構造確認
DESCRIBE local_import_audit_log;

-- インデックス確認
SHOW INDEX FROM local_import_audit_log;
```

### 3. アプリケーション起動・再起動

**Docker:**
```powershell
# 再起動
docker compose restart web

# ログ確認
docker compose logs web --tail 100 | Select-String "監査"
```

**ローカル:**
```powershell
# 起動
python main.py

# 期待されるログ:
# "Local Import監査ロガーを初期化しました"
```

### 4. API動作確認

```powershell
# ヘルスチェック
curl http://localhost:5000/health

# Swagger UI
# ブラウザで http://localhost:5000/api/docs を開く

# APIテスト（セッションIDは実際の値に置き換え）
curl http://localhost:5000/api/local-import/sessions/1/status

# PowerShellの場合
Invoke-WebRequest -Uri "http://localhost:5000/api/local-import/sessions/1/status" | Select-Object -Expand Content
```

---

## 🐛 トラブルシューティング

### 問題: "docker compose" コマンドが見つからない

**解決策:**
```powershell
# Docker Desktopがインストールされているか確認
docker --version

# 旧バージョンの場合
docker-compose ps

# 代わりにローカルPython環境を使用
```

### 問題: Pythonコマンドが見つからない

**解決策:**
```powershell
# 利用可能なPythonを探す
where.exe python
where.exe python3
where.exe py

# Pythonがない場合はDockerを使用
docker compose exec web flask db upgrade
```

### 問題: "Can't connect to database"

**解決策:**
```powershell
# .envファイルを確認
Get-Content .env | Select-String "DATABASE"

# Dockerの場合、DBコンテナが起動しているか確認
docker compose ps db

# DBコンテナを起動
docker compose up -d db
docker compose up -d web
```

### 問題: マイグレーション履歴の不整合

**解決策:**
```powershell
# 現在の状態確認
flask db current
flask db history | Select-Object -First 10

# 強制的にrevisionを設定（慎重に使用）
flask db stamp a1b2c3d4e5f6
```

---

## 📊 成功した場合の出力例

### マイグレーション実行
```
INFO  [alembic.runtime.migration] Context impl MySQLImpl.
INFO  [alembic.runtime.migration] Will assume non-transactional DDL.
INFO  [alembic.runtime.migration] Running upgrade a4e3d9f2c5ab -> a1b2c3d4e5f6, add local_import_audit_log table
```

### アプリケーション起動
```
INFO in __init__: Local Import監査ロガーを初期化しました
INFO in _helpers: * Running on http://127.0.0.1:5000
```

### API呼び出し
```json
{
  "session_id": 1,
  "state": "pending",
  "stats": {
    "total": 0,
    "success": 0,
    "failed": 0,
    "processing": 0
  },
  "last_updated": "2024-12-28T10:00:00Z"
}
```

---

## 🎉 次のPhaseへ

マイグレーション成功後：

1. **Phase 1完了** - 監査ログシステムが稼働中
2. **Phase 2準備** - `integration_example.py` を参照して既存コードに統合
3. **UI確認** - Vue componentを既存ページに追加

---

## 📞 クイックヘルプ

**最も簡単な方法（Docker使用）:**
```powershell
docker compose exec web flask db upgrade
docker compose restart web
docker compose logs web --tail 50
```

**ローカル環境で実行:**
```powershell
python -m flask db upgrade
python main.py
```

**確認:**
```powershell
curl http://localhost:5000/api/docs
```

問題が発生した場合は、上記のトラブルシューティングセクションを参照してください。
