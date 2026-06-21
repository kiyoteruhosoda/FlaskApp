# シングルサーバー構成ガイド

## 概要

**1つのFlaskサーバー（ポート5000）** で開発・本番両方に対応できるようになりました。

## アーキテクチャ

### 開発モード
```
ブラウザ → Flask(5000) → Vite(3000) プロキシ
                ↓
              API処理
```

Flaskが全てのリクエストを受け取り：
- APIリクエスト（`/api/*`）→ Flask内部で処理
- 静的ファイル（`/assets/*`, `/src/*`, `/@vite/*`）→ Viteにプロキシ
- HTMLページ → Viteにプロキシ

### 本番モード
```
ブラウザ → Flask(5000)
           ├→ API処理
           └→ ビルド済みファイル配信
```

## 使い方

### 1. 開発モード（推奨）

#### ターミナル1: Viteを起動
```bash
cd frontend
npm run dev
```

#### ターミナル2: Flaskを起動
```bash
source /home/kyon/myproject/.venv/bin/activate
python main.py
```

#### アクセス
- **http://localhost:5000** にアクセスするだけ
- Viteが自動でプロキシされる
- Hot Module Replacement (HMR) が動作

### 2. 本番モード

#### ビルド
```bash
cd frontend
npm run build
```

#### Flaskを本番モードで起動
```bash
source /home/kyon/myproject/.venv/bin/activate
FLASK_ENV=production python main.py
```

#### アクセス
- **http://localhost:5000** にアクセス
- ビルド済みファイルが配信される

### 3. 開発モード（Viteなし）

Viteを起動せずにFlaskだけを起動した場合：

```bash
source /home/kyon/myproject/.venv/bin/activate
python main.py
```

**http://localhost:5000** にアクセスすると、親切なエラーメッセージが表示されます：

```
⚠️ Viteサーバーが起動していません

開発モードで動作させるには、Viteサーバーを起動してください：
cd frontend && npm run dev

またはビルドしたファイルを使用してください：
cd frontend && npm run build
```

## メリット

✅ **シンプル**: 常に `http://localhost:5000` にアクセスするだけ  
✅ **高速開発**: Viteのホットリロードをそのまま利用  
✅ **統一**: 開発・本番で同じURLパス  
✅ **柔軟**: Viteあり・なし両方に対応  

## 技術詳細

### プロキシ実装

[react_routes.py](presentation/web/react_routes.py) の `proxy_to_vite()` 関数：

```python
def proxy_to_vite(path=''):
    """開発時にViteサーバーにプロキシ"""
    try:
        vite_url = f"{VITE_DEV_SERVER}/{path}"
        resp = requests.get(vite_url, stream=True, timeout=5)
        
        # Viteからのレスポンスをそのまま返す
        response = Response(generate(), status=resp.status_code)
        
        # ヘッダーをコピー（一部除外）
        excluded_headers = ['content-encoding', 'content-length', 'transfer-encoding', 'connection']
        for name, value in resp.headers.items():
            if name.lower() not in excluded_headers:
                response.headers[name] = value
                
        return response
    except requests.exceptions.RequestException as e:
        # エラー時は親切なメッセージを表示
        return error_message, 503
```

### 環境変数

- `VITE_DEV_SERVER`: Viteサーバーのアドレス（デフォルト: `http://localhost:3000`）
- `FLASK_ENV`: `development` または `production`
- `FLASK_DEBUG`: `1` で開発モード

## トラブルシューティング

### 1. 503 エラー（Vite未起動）

**原因**: 開発モードだがViteが起動していない

**解決策**:
```bash
cd frontend && npm run dev
```

### 2. ページが真っ白

**原因**: 本番モードだがビルドファイルがない

**解決策**:
```bash
cd frontend && npm run build
```

### 3. APIエラー

**確認方法**:
```bash
curl http://localhost:5000/api/auth/check
```

Flask側のログを確認してください。

## 旧構成との比較

### 旧構成（2サーバー）
```
開発時:
  ブラウザ → Vite(3000) → API(5000)
  
本番時:
  ブラウザ → Flask(5000)
```

問題点:
- ポートが2つ必要
- URLが環境で異なる
- 開発時にCORS設定が必要

### 新構成（1サーバー）
```
常に:
  ブラウザ → Flask(5000)
```

メリット:
- ポート1つだけ
- URLが常に同じ
- CORS不要
