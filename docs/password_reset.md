# パスワードリセット機能

## 概要

ユーザーがパスワードを忘れた場合に、メール経由でパスワードを再設定できる機能です。

## 機能

### 1. パスワードリセットリクエスト

- URL: `/auth/password/forgot`
- ユーザーがメールアドレスを入力
- システムがリセット用のトークンを生成し、メールで送信
- セキュリティ上、メールアドレスの存在有無に関わらず同じメッセージを表示

### 2. パスワードリセット

- URL: `/auth/password/reset?token=<token>`
- ユーザーが新しいパスワードを2回入力
- トークンが有効な場合のみパスワードを更新
- パスワードは8文字以上が必要

## セキュリティ機能

### トークンのセキュリティ

- **256ビットのランダムトークン**: `secrets.token_urlsafe()` を使用した暗号論的に安全なトークン生成
- **ハッシュ化保存**: トークンはデータベースにハッシュ化して保存（平文での保存は行わない）
- **有効期限**: トークンは30分で期限切れ
- **ワンタイム使用**: トークンは一度使用すると無効化され、再利用不可

### プライバシー保護

- **アカウント存在確認攻撃への対策**: メールアドレスが存在するかどうかに関わらず、常に同じ成功メッセージを表示
- **タイミング攻撃への対策**: レスポンスタイムが一定になるよう実装

### パスワード要件

- 最低8文字
- 確認用パスワードが一致すること

## メール設定

パスワードリセット機能を使用するには、以下の環境変数を設定する必要があります：

```bash
# .env ファイルに以下を追加
MAIL_SERVER=smtp.gmail.com          # SMTPサーバー
MAIL_PORT=587                        # SMTPポート
MAIL_USE_TLS=True                    # TLS使用
MAIL_USE_SSL=False                   # SSL使用（通常はFalse）
MAIL_USERNAME=your-email@example.com # メールアカウント
MAIL_PASSWORD=your-app-password      # アプリパスワード
MAIL_DEFAULT_SENDER=your-email@example.com # 送信元アドレス
```

### Gmailの場合

1. Googleアカウントで2段階認証を有効化
2. アプリパスワードを生成: https://myaccount.google.com/apppasswords
3. 生成されたアプリパスワードを `MAIL_PASSWORD` に設定

## データベース

### password_reset_token テーブル

| カラム名 | 型 | 説明 |
|---------|-----|------|
| id | bigint | 主キー |
| email | varchar(255) | リセット対象のメールアドレス |
| token_hash | varchar(255) | トークンのハッシュ値（ユニーク） |
| expires_at | datetime | トークンの有効期限 |
| used | boolean | 使用済みフラグ |
| created_at | datetime | 作成日時 |

### マイグレーション

```bash
# マイグレーションの適用
flask db upgrade
```

## API仕様

### POST /auth/password/forgot

パスワードリセットメールを送信

**リクエスト:**
```json
{
  "email": "user@example.com"
}
```

**レスポンス:**
- 成功時: ログイン画面にリダイレクト、成功メッセージ表示
- 失敗時: 入力画面を再表示、エラーメッセージ表示

### GET /auth/password/reset?token=<token>

パスワードリセット画面を表示

**パラメータ:**
- `token`: リセットトークン（必須）

**レスポンス:**
- 有効なトークン: パスワード入力画面を表示
- 無効なトークン: ログイン画面にリダイレクト、エラーメッセージ表示

### POST /auth/password/reset

パスワードをリセット

**リクエスト:**
```json
{
  "token": "reset-token-here",
  "password": "newpassword123",
  "password_confirm": "newpassword123"
}
```

**レスポンス:**
- 成功時: ログイン画面にリダイレクト、成功メッセージ表示
- 失敗時: リセット画面を再表示、エラーメッセージ表示

## 使用例

### ユーザー視点のフロー

1. ログイン画面で「パスワードを忘れた方はこちら」リンクをクリック
2. メールアドレスを入力して送信
3. 受信したメール内のリンクをクリック
4. 新しいパスワードを2回入力して送信
5. ログイン画面に戻り、新しいパスワードでログイン

### 開発者向け：プログラムからの利用

```python
from webapp.services.password_reset_service import PasswordResetService

# リセットリクエストの作成
PasswordResetService.create_reset_request("user@example.com")

# トークンの検証
email = PasswordResetService.verify_token("token-here")
if email:
    # トークンが有効

# パスワードのリセット
success = PasswordResetService.reset_password("token-here", "new-password")
```

## テスト

```bash
# パスワードリセット機能のテストを実行
pytest tests/webapp/auth/test_password_reset.py -v
```

テストカバレッジ:
- トークン生成
- リセットリクエスト作成（アクティブユーザー、非アクティブユーザー、存在しないユーザー）
- トークン検証（有効、無効、期限切れ、使用済み）
- パスワードリセット（成功、失敗、再利用防止）
- ルートテスト（GET/POST、バリデーション）

## トラブルシューティング

### メールが送信されない

1. SMTP設定を確認
2. ファイアウォールでSMTPポート（587）が開いているか確認
3. メールプロバイダーのセキュリティ設定を確認（Gmailの場合は2段階認証とアプリパスワード）

### トークンが無効と表示される

- トークンの有効期限（30分）を確認
- データベース接続を確認
- ログを確認（`webapp:password_reset_service.py`）

### パスワードリセット後もログインできない

- 新しいパスワードが正しく設定されているかデータベースを確認
- ブラウザのキャッシュをクリア
- セッションをクリア

## セキュリティのベストプラクティス

1. **環境変数の保護**: `.env` ファイルは`.gitignore`に含め、本番環境でのみ設定
2. **HTTPS使用**: 本番環境では必ずHTTPSを使用
3. **レート制限**: リセットリクエストに対してレート制限を実装することを推奨
4. **ログ監視**: 異常なリセット試行を監視
5. **パスワードポリシー**: より強力なパスワード要件の追加を検討

## 今後の改善案

- [ ] レート制限の実装（同一メールアドレスに対する連続リクエスト制限）
- [ ] パスワード強度チェックの強化
- [ ] リセット履歴の記録
- [ ] メール送信の非同期処理化（Celeryタスク化）
- [ ] 多言語対応の強化
