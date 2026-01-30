# フロントエンド関連タスク

.PHONY: frontend-install frontend-build frontend-dev frontend-clean

# フロントエンドの依存関係をインストール
frontend-install:
	cd frontend && npm install

# フロントエンドをビルド
frontend-build: frontend-install
	cd frontend && npm run build

# フロントエンド開発サーバーを起動
frontend-dev:
	cd frontend && npm start

# フロントエンドをクリーン
frontend-clean:
	rm -rf frontend/node_modules
	rm -rf frontend/build
	rm -rf frontend/.eslintcache

# フルビルド（バックエンド + フロントエンド）
build-all: frontend-build

# 開発環境セットアップ
dev-setup: frontend-install
	@echo "Development environment setup complete"

# プロダクションビルド
production-build: frontend-build
	@echo "Production build complete"