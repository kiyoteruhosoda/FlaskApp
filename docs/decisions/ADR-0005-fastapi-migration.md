# ADR-0005: FastAPI 全面移行（Flask-Smorest → FastAPI）

- ステータス: Accepted
- 日付: 2026-07-08

## コンテキスト

現行のバックエンド API は Flask + Flask-Smorest で実装されている。以下の課題が蓄積している：

- Flask-Smorest の OpenAPI 自動生成は装飾的な `@bp.doc` / Marshmallow Schema の二重定義を要求し、保守コストが高い
- Flask は WSGI ベースのため、async/await による非同期処理（WebSocket、Server-Sent Events 等）が標準では使えない
- `current_app.logger`・`g`・`session` など Flask のグローバル代理オブジェクトへの依存が深く、単体テストが書きにくい
- Pydantic v2 を活用した型安全性・パフォーマンス向上が Flask-Smorest では制限される

FastAPI への移行で以下が得られる：
- Pydantic モデルによる型安全なリクエスト/レスポンス定義（二重定義が不要）
- OpenAPI スキーマの自動生成（Swagger UI / ReDoc）
- 非同期エンドポイントのネイティブサポート
- FastAPI `Depends()` による明示的な依存注入（テスタビリティ向上）
- uvicorn / anyio による ASGI ランタイム

## 決定

**Strangler Fig パターン**（段階的絞め込み移行）を採用する。

### 移行順序

#### フェーズ 1: Foundation（本 PR）
1. `presentation/fastapi/` に FastAPI アプリレイヤーを新設する
2. `shared/kernel/database/session.py` に Flask 非依存の SQLAlchemy セッションファクトリを追加する
3. JWT 認証依存コンポーネント（`Depends` ベース）を実装する
4. 全 API ルート（`/api/*`）を FastAPI `APIRouter` へ移行する
5. `asgi.py` を新設し、FastAPI が `/api/*` を処理、Flask が UI ルート（`/auth/*` `/dashboard/*` 等）を処理する ASGI エントリポイントとする
6. `TokenService` を Flask コンテキスト非依存に修正する（`current_app.logger` → `logging.getLogger()`）

#### フェーズ 2: UI 層移行（次 PR 以降）
- Flask テンプレート（Jinja2）ルートを FastAPI + Jinja2 テンプレートに移行する
- `flask-babel` → `babel` 直接使用に切り替える
- `flask-login` セッション管理を廃止し、JWT 専一化する

#### フェーズ 3: Flask 完全撤廃
- `flask` / `flask-smorest` / `flask-sqlalchemy` / `flask-migrate` / `flask-login` / `flask-babel` を削除する
- `migration` は Alembic 直接実行に切り替える

### 共存戦略（フェーズ 1）

```
uvicorn asgi:app
├── FastAPI  /api/*          ← 新規（本 PR で移行）
└── WSGIMiddleware(Flask)    ← 既存 UI ルートをそのまま保持
    ├── /auth/*
    ├── /dashboard/*
    ├── /admin/*             （UI ページ）
    ├── /wiki/*
    └── /certs/              （UI ページ）
```

`a2wsgi.WSGIMiddleware` を使用して Flask WSGI アプリを ASGI ミドルウェアとしてマウントする。

### DB セッション管理

- `shared/kernel/database/session.py` に `create_session_factory()` を追加する
- FastAPI ルートでは `Depends(get_db)` でセッションを注入する
- 移行完了まで `shared/kernel/database/db.py`（Flask-SQLAlchemy）と共存させる

### 認証

- FastAPI 側では JWT のみをサポートする（`flask-login` セッション認証は Flask 側で引き続き処理）
- `OAuth2PasswordBearer` を使用して ******
- `TokenService.verify_access_token()` は Flask 非依存のため再利用する

## 選択肢と理由

- **案A（採用）: Strangler Fig + ASGI マウント**
  Flask WSGI を FastAPI の中にマウントしてルート単位で段階的に移行する。リスクが低く、既存の UI/セッション機能を壊さずに API 移行を進められる。

- **案B: 完全書き換え**
  Flask を全て削除して FastAPI に一気に書き直す。リスクが高く、UI 層・Celery 連携・マイグレーション等の多方面に影響する。工数が大きすぎてリリースが長期間停止する。

- **案C: nginx 分岐**
  nginx レベルで `/api/*` を FastAPI サーバー、それ以外を Flask サーバーに振り分ける。インフラ変更が必要でデプロイが複雑化する。ASGI マウントの方がシンプル。

## 影響

- **良い点**: API ルートの型安全性・テスタビリティ向上。OpenAPI ドキュメントが自動生成される。
- **トレードオフ**: 移行期間中は Flask と FastAPI が共存するため、DB セッションが 2 系統存在する（`db.session` と `Depends(get_db)`）。
- **移行完了まで**: `shared/kernel/database/db.py` を削除できない。
- **テスト**: `pytest` + `httpx` + `TestClient` で FastAPI エンドポイントをテストする。既存の Flask テストは変更なし。
- **Celery**: タスク実装は変更しない。FastAPI エンドポイントから Celery タスクを `.delay()` / `.apply_async()` で呼び出す形は変わらない。
