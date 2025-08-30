#!/bin/bash
# 本番環境デプロイスクリプト

set -e

echo "PhotoNest 本番環境デプロイを開始します..."

# 本番環境用の依存関係をインストール
echo "依存関係をインストール中..."
pip install -r requirements-prod.txt

# データベースマイグレーション
echo "データベースをマイグレーション中..."
export FLASK_APP=wsgi.py
flask db upgrade

# 静的ファイルの準備（必要に応じて）
echo "静的ファイルを準備中..."
# python manage.py collectstatic --noinput

# 翻訳ファイルのコンパイル
echo "翻訳ファイルをコンパイル中..."
pybabel compile -d webapp/translations -f

# セキュリティチェック（オプション）
echo "セキュリティチェックを実行中..."
# python -m safety check

echo "デプロイが完了しました！"
echo "アプリケーションを起動するには: gunicorn --bind 0.0.0.0:5000 --workers 4 wsgi:app"
