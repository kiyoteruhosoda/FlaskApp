# ADR-0006: ユーザースイッチ（Impersonation）設計

- ステータス: Accepted
- 日付: 2026-07-08

## コンテキスト

運用管理者（`admin:impersonate` 権限保持者）が他のユーザーに成り代わって
画面・機能を確認できる Impersonation 機能を実装する。

要件：
- 管理者が対象ユーザーを指定して成り代わりセッションを開始できる
- 成り代わり中は「誰の代わりに操作しているか」が JWT クレームに記録される
- 元の管理者トークンで成り代わりを終了できる
- 成り代わりの開始・終了・中間操作を**監査ログ**に記録する（誰が、いつ、誰に）
- 成り代わり中も元の管理者 ID を保持し、成り代わりユーザーへ昇権はしない

## 決定

### 認証方式

JWT クレームに `impersonator_id`（元の管理者 ID）と `impersonated_id`（対象ユーザー ID）を追加する。

- **成り代わり開始** (`POST /api/admin/impersonation/start`):
  - 管理者の JWT を検証し、`admin:impersonate` 権限を確認
  - 対象ユーザーの権限で新しい短命アクセストークン（TTL: 1時間）を発行
  - 新トークンには `impersonator_id: <admin_id>` クレームを追加
  - 元のリフレッシュトークンは変えない
  - 監査ログ（`ImpersonationAuditLog`）に STARTED イベントを記録

- **成り代わり終了** (`POST /api/admin/impersonation/end`):
  - 成り代わりトークンを受け取り、`impersonator_id` から元の管理者を特定
  - 管理者として再ログインするための新トークンを発行
  - 監査ログに ENDED イベントを記録

### 監査ログ設計

`impersonation_audit_log` テーブルを新設する。

| カラム | 型 | 説明 |
|---|---|---|
| id | BIGINT PK | |
| impersonator_id | BIGINT FK(users) | 成り代わった管理者 |
| impersonated_id | BIGINT FK(users) | 成り代わられたユーザー |
| event | VARCHAR(16) | STARTED / ENDED |
| ip_address | VARCHAR(45) | クライアント IP |
| user_agent | TEXT NULLABLE | |
| created_at | DATETIME | UTC |

### 権限コード

`admin:impersonate` を新設。`admin` ロールのみに付与する。

### 対象外の設計

- 成り代わり中のトークンリフレッシュは許可しない（TTL 1時間で強制終了）
- サービスアカウントへの成り代わりは禁止
- 管理者への成り代わりは禁止（権限エスカレーション防止）

## 選択肢と理由

- **案A（採用）: JWT クレームで impersonator_id を付与**
  - セッションレスで、FastAPI の JWT 認証と完全に整合する
  - トークンさえあればどのワーカーでも検証可能
  - 短命トークン（1時間）で成り代わりの影響範囲を限定できる

- **案B: Flask-Login セッションで状態を保持**
  - JWT 専一化の方針（T11）と矛盾する。不採用。

- **案C: Redis で成り代わりセッションを管理**
  - Redis 依存が増える。JWT で十分表現できる。不採用。

## 影響

- `shared/domain/auth/master_data.py` に `admin:impersonate` を追加
- マイグレーション: `impersonation_audit_log` テーブル作成 + 権限シード
- FastAPI ルーター: `presentation/fastapi/routers/admin/impersonation.py`
- 成り代わり中は `TokenService.create_principal_from_token()` が
  `impersonator_id` クレームを検出してプリンシパルへ反映する
