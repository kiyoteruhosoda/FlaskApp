# バージョン情報機能

このアプリケーションには、リリースのたびに自動的に更新されるバージョン情報表示機能が実装されています。

## 機能概要

- ビルド時に生成されるバージョンファイル（`core/version.json`）ベース
- Gitコミットハッシュをベースとしたバージョン文字列
- 本番環境でGitに依存しない仕組み
- Web UI、API、CLIから確認可能

## バージョン情報の表示方法

### 1. Web UI での表示

#### フッター表示
すべてのページのフッターに簡易バージョン情報が表示されます。

#### 管理者ページ
管理者権限を持つユーザーは、詳細なバージョン情報ページにアクセスできます：
- URL: `/admin/version`
- ナビゲーション: Admin → Version Info

### 2. API エンドポイント

```bash
GET /api/version
```

レスポンス例：
```json
{
  "ok": true,
  "version": "va0b7e23",
  "details": {
    "version": "va0b7e23",
    "commit_hash": "a0b7e23",
    "commit_hash_full": "a0b7e2319a4c44e85a76c731245226e3d5910118",
    "branch": "main",
    "commit_date": "2025-09-07 15:30:16 +0900",
    "build_date": "2025-09-07T17:18:32+09:00",
    "app_start_date": "2025-09-07T17:22:17.270537"
  }
}
```

### 3. Flask CLI コマンド

```bash
flask version
```

出力例：
```
=== PhotoNest Version Information ===
Version: va0b7e23
Commit Hash: a0b7e23
Branch: main
Commit Date: 2025-09-07 15:30:16 +0900
Build Date: 2025-09-07T17:18:32+09:00
```

## バージョン文字列の形式

- メインブランチ: `v{コミットハッシュ}` (例: `va0b7e23`)
- その他ブランチ: `v{コミットハッシュ}-{ブランチ名}` (例: `va0b7e23-feature`)

## ビルド・デプロイ手順

### 1. 開発環境でのバージョンファイル生成

```bash
# プロジェクトルートで実行
./scripts/generate_version.sh
```

### 2. Docker でのビルド

Dockerビルド時に自動的にバージョンファイルが生成されます：

```bash
docker build -t photonest:latest .
```

ビルドステージで以下が実行されます：
1. Gitから現在のコミット情報を取得
2. `core/version.json` ファイルを生成
3. 実行ステージにバージョンファイルをコピー

### 3. 本番デプロイ

本番環境ではGitが不要です。生成済みの `core/version.json` ファイルからバージョン情報が読み込まれます。

## 技術的詳細

### バージョンファイルの構造

`core/version.json`:
```json
{
    "version": "va0b7e23",
    "commit_hash": "a0b7e23",
    "commit_hash_full": "a0b7e2319a4c44e85a76c731245226e3d5910118",
    "branch": "main",
    "commit_date": "2025-09-07 15:30:16 +0900",
    "build_date": "2025-09-07T17:18:32+09:00"
}
```

### バージョン情報の取得順序

1. `core/version.json` ファイルからの読み込み（推奨）
2. ファイルが存在しない場合はデフォルト値 (`"dev"`)

### ファイル構成

- `/core/version.py` - バージョン情報取得のコアロジック
- `/core/version.json` - ビルド時に生成されるバージョンファイル
- `/scripts/generate_version.sh` - バージョンファイル生成スクリプト
- `/webapp/api/version.py` - バージョン情報API
- `/webapp/admin/templates/version_view.html` - 管理者向け詳細表示
- `/webapp/templates/base.html` - フッター表示

### CI/CD での利用

CI/CD パイプラインでは、Dockerビルド時に自動的にバージョンファイルが生成されます：

```yaml
# GitHub Actions の例
- name: Build Docker image
  run: docker build -t photonest:latest .
```

## 利点

- **確実性**: リリースのたびに必ず変更される
- **追跡可能性**: 特定のコミットに紐づけられる
- **軽量**: 短縮ハッシュで簡潔
- **本番環境対応**: Gitに依存しない
- **開発環境フレンドリー**: 開発時は動的にバージョンファイルを生成可能
