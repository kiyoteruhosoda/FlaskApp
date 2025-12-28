# Google OAuth HTTPS 修正実装記録

## 問題
GoogleのOAuth認証リダイレクトURLが `http://n.nolumia.com/auth/google/callback` になっており、httpsになっていない。

## 実装した修正

### 1. 環境変数設定 (.env)
```bash
# URL生成設定 (OAuth redirects)
PREFERRED_URL_SCHEME=https
```

### 2. Flask設定の更新 (webapp/config.py)
```python
# URL生成設定
PREFERRED_URL_SCHEME = os.environ.get("PREFERRED_URL_SCHEME", "http")
```

### 3. ProxyFix ミドルウェア追加 (webapp/__init__.py)
```python
from werkzeug.middleware.proxy_fix import ProxyFix

# リバースプロキシ（nginx等）使用時のHTTPS検出
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)
```

### 4. デバッグ機能追加
- デバッグエンドポイント: `/debug/headers`, `/debug/oauth-url`
- 詳細ログ出力（DebugProxyFix）
- 包括的テストスイート: `tests/test_oauth_https.py`

## 動作確認
テストスクリプト `test_oauth_url.py` で確認済み：
- `X-Forwarded-Proto: https` ヘッダー存在時
- コールバックURL: `https://localhost/auth/google/callback`
- OAuth URL: httpsスキームで正しく生成

## 本番環境での設定要件

### 1. 環境変数
```bash
PREFERRED_URL_SCHEME=https
```

### 2. リバースプロキシ設定（nginx例）
```nginx
server {
    listen 443 ssl;
    server_name n.nolumia.com;
    
    location / {
        proxy_pass http://backend;
        proxy_set_header X-Forwarded-Proto $scheme;  # 最重要
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 3. Google Cloud Console設定
- 認証済みリダイレクトURIに本番ドメインのhttps URLを追加
- 例: `https://n.nolumia.com/auth/google/callback`

## トラブルシューティング

### 問題: まだhttpになってしまう場合

#### 1. デバッグエンドポイントで確認
```bash
curl -H "X-Forwarded-Proto: https" https://n.nolumia.com/debug/headers
curl -H "X-Forwarded-Proto: https" https://n.nolumia.com/debug/oauth-url
```

#### 2. nginx設定の確認
```bash
# nginx設定ファイルの確認
sudo nginx -t
sudo grep -r "proxy_set_header.*X-Forwarded-Proto" /etc/nginx/

# nginxのアクセスログで実際のヘッダーを確認
sudo tail -f /var/log/nginx/access.log
```

#### 3. アプリケーションログの確認
```bash
# DebugProxyFixのログを確認
grep "ProxyFix" /path/to/app.log

# Flask アプリケーションのログを確認
grep "PREFERRED_URL_SCHEME" /path/to/app.log
```

#### 4. 環境変数の確認
```bash
# 実行中のプロセスで環境変数を確認
ps aux | grep python
cat /proc/[PID]/environ | tr '\0' '\n' | grep PREFERRED_URL_SCHEME
```

### よくある原因

1. **nginx設定不備**: `proxy_set_header X-Forwarded-Proto $scheme;` が設定されていない
2. **環境変数未設定**: `PREFERRED_URL_SCHEME=https` が設定されていない  
3. **ProxyFix設定不備**: ミドルウェアが正しく適用されていない
4. **SSL終端の問題**: SSLがnginxで終端され、バックエンドにHTTPで転送されている

### 検証手順
1. テストの実行: `python -m pytest tests/test_oauth_https.py -v`
2. デバッグエンドポイントでの確認
3. 実際のOAuth フローのテスト

## 注意事項
- 開発環境では `http://localhost:5000/auth/google/callback` のまま
- 本番環境でのみ `PREFERRED_URL_SCHEME=https` を設定
- リバースプロキシが適切な `X-Forwarded-Proto` ヘッダーを送信することが必要
- Google Cloud ConsoleでリダイレクトURIの追加を忘れずに
