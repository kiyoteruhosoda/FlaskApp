# PhotoNest Frontend Development Guide

## なぜ2つのサーバーが必要なのか？

### 開発環境（2つのサーバー）
開発中は **Vite（ポート3000）** と **Flask（ポート5000）** の2つのサーバーを起動します：

**Vite開発サーバー（ポート3000）の役割：**
- ⚡ **高速なホットリロード**：コード変更を即座に反映（リフレッシュ不要）
- 🔥 **Fast Refresh**：Reactコンポーネントの状態を保持したまま更新
- 📦 **ESモジュール配信**：ビルド不要で高速起動
- 🐛 **ソースマップ**：元のTypeScriptコードでデバッグ可能
- 🎨 **CSSホットリロード**：スタイル変更も即座に反映

**Flask APIサーバー（ポート5000）の役割：**
- 🔐 **認証・認可**：ログイン、JWT発行、セッション管理
- 📊 **データベース操作**：MariaDBへのアクセス
- 🖼️ **メディア処理**：画像・動画の変換、サムネイル生成
- 🔄 **Google Photos同期**：外部API連携

Viteは `/api/*` へのリクエストを自動的にFlaskにプロキシします。

```
開発環境の構成:
┌─────────────────┐
│  ブラウザ        │
│ localhost:3000  │
└────────┬────────┘
         │
         │ (HTML/CSS/JSはここから)
         ▼
┌─────────────────┐      /api/* のリクエスト      ┌─────────────────┐
│  Vite Server    │ ────────────────────────────▶│  Flask Server   │
│  (Port 3000)    │                               │  (Port 5000)    │
│                 │◀────────────────────────────  │                 │
│ - ホットリロード │         APIレスポンス         │ - API処理       │
│ - Fast Refresh  │                               │ - DB操作        │
│ - ソースマップ   │                               │ - 認証          │
└─────────────────┘                               └─────────────────┘
```

### 本番環境（1つのサーバー）
本番環境では **Flaskのみ（ポート5000）** で動作します：

```bash
# Reactをビルド
cd frontend
npm run build  # → build/ ディレクトリに静的ファイルを生成

# Flaskが静的ファイルとAPIの両方を配信
cd ..
python main.py  # → http://localhost:5000 で全て処理
```

**本番環境の仕組み：**
1. Reactをビルドすると `build/` に静的ファイル（HTML/CSS/JS）が生成される
2. Flaskは `/api/*` 以外のリクエストを静的ファイルから配信
3. APIリクエストは通常通りFlaskが処理
4. **結果：1つのサーバーで完結**

```
本番環境の構成:
┌─────────────────┐
│  ブラウザ        │
│ localhost:5000  │
└────────┬────────┘
         │
         │ すべてのリクエスト
         ▼
┌──────────────────────────────────┐
│      Flask Server (Port 5000)    │
│                                  │
│  /api/*          → API処理      │
│  /login, /       → build/index.html を返す │
│  /assets/*       → build/assets/* を返す   │
│                                  │
│  build/                          │
│  ├── index.html  (React SPA)     │
│  ├── assets/                     │
│  │   ├── index-abc123.js         │
│  │   └── index-def456.css        │
│  └── favicon.ico                 │
└──────────────────────────────────┘
```

### 開発環境のメリット
- コード変更が1秒以内に反映される
- ビルド時間を待たずに開発できる
- 開発者体験が圧倒的に向上

### 本番環境への移行
開発が完了したら、以下のコマンドで本番用にビルドします：
```bash
cd frontend
npm run build
```
これで `build/` ディレクトリが生成され、Flaskだけで動作可能になります。

**本番環境での起動：**
```bash
# 開発モードを無効化
export FLASK_ENV=production
export FLASK_DEBUG=0

# Flaskサーバー起動（本番用）
python main.py
# または Gunicorn を使用
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
```

この場合、`http://localhost:5000` にアクセスすると：
- `/api/*` → Flask APIが処理
- `/login`, `/dashboard`, etc → `build/index.html` が配信される（React Router でクライアントサイドルーティング）
- `/assets/*` → ビルドされたJS/CSS/画像ファイルが配信される

---

## 開発環境のセットアップ

### 必要な環境
- Node.js 18以上
- npm 9以上

### インストール
```bash
cd frontend
npm install
```

## 開発サーバーの起動

### 基本的な起動
```bash
npm run dev
```
デフォルトで `http://localhost:3000` で起動します。

### デバッグモードで起動
```bash
npm run dev:debug
```
詳細なログが出力されます。

### 外部アクセスを許可して起動
```bash
npm run dev:host
```
`http://0.0.0.0:3000` で起動し、ネットワーク内の他のデバイスからアクセス可能になります。

## Flask APIサーバーとの連携

### 前提条件
Flask APIサーバーが `http://localhost:5000` で起動している必要があります。

```bash
# 別のターミナルで
cd /work/project/FlaskApp
source .venv/bin/activate  # 仮想環境がある場合
python main.py
```

### プロキシ設定
`vite.config.ts` で以下のように設定されています：

- `/api/*` → `http://localhost:5000/api/*` にプロキシ
- `/auth/*` → `http://localhost:5000/auth/*` にプロキシ

### 動作確認
1. Flask APIサーバーを起動: `python main.py`
2. Vite開発サーバーを起動: `npm run dev`
3. ブラウザで `http://localhost:3000` を開く
4. ログインページで認証情報を入力

## ビルド

### プロダクションビルド
```bash
npm run build
```
`build/` ディレクトリにビルド成果物が出力されます。

### ビルド結果のプレビュー
```bash
npm run preview
```

### ウォッチモード（開発用）
```bash
npm run build:watch
```
ファイル変更時に自動的に再ビルドされます。

## コード品質チェック

### TypeScript型チェック
```bash
npm run type-check
```

### ESLintチェック
```bash
npm run lint
```

## VSCodeでのデバッグ

### React開発サーバーのデバッグ
1. VSCodeのデバッグパネルを開く
2. 「Chrome: React Dev Server」を選択
3. デバッグ開始（F5）

### Flask + Reactの同時デバッグ
1. VSCodeのデバッグパネルを開く
2. 「Full Stack: Flask + React」を選択
3. デバッグ開始（F5）

## トラブルシューティング

### ポートが使用中の場合
```bash
# ポート3000を使用しているプロセスを確認
lsof -i :3000
# プロセスを終了
kill -9 <PID>
```

### プロキシエラーの場合
1. Flask APIサーバーが起動しているか確認
2. `vite.config.ts` のプロキシ設定を確認
3. ブラウザのコンソールログを確認

### キャッシュクリア
```bash
npm run clean
npm install
```

## 環境変数

`.env` ファイルで環境変数を設定できます（作成する場合）：

```env
VITE_API_BASE_URL=http://localhost:5000
VITE_APP_NAME=PhotoNest
```

コード内での使用:
```typescript
const apiUrl = import.meta.env.VITE_API_BASE_URL;
```

## 参考リンク

- [Vite Documentation](https://vitejs.dev/)
- [React Documentation](https://react.dev/)
- [Redux Toolkit Documentation](https://redux-toolkit.js.org/)
- [React Bootstrap Documentation](https://react-bootstrap.github.io/)
