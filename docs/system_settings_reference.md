# システム設定仕様書

`system_settings` テーブルで管理する永続設定の一覧と JSON 構造をまとめた設計ドキュメントです。アプリケーションは **ここで定義したキーとプロパティのみを利用** し、定義されていない値は読み飛ばします。運用時は DB 内の JSON を直接編集するか、初期投入スクリプトを用いて更新します。

## 1. テーブルと保持ルール

| 項目 | 内容 |
| --- | --- |
| テーブル名 | `system_settings` |
| 主キー | `id` (AUTO_INCREMENT) |
| 論理キー | `setting_key`（ユニーク） |
| 設定値 | `setting_json` 列に JSON 形式で保存 |
| 更新メタ情報 | `updated_at`（自動更新）、`description`（任意の備考） |

- 監査用の時刻はテーブルの `updated_at` に自動で記録されるため、JSON 内に重複した日時フィールドを入れる必要はありません。
- 変更者の追跡が必要な場合はアプリ側の監査ログ、もしくは `description` に記載してください（JSON では管理しません）。

## 2. 設定キーの整理

`setting_key` は用途ごとに prefix を付けた名前空間で管理します。現在アプリが参照するキーは次の 3 種類です。

| setting_key | 管理カテゴリ | 主な読み出し元 | JSON の役割 |
| --- | --- | --- | --- |
| `access_token_signing` | アクセストークン署名設定 | `SystemSettingService.get_access_token_signing_setting()` | 署名モードと証明書識別子を保持 |
| `app.config` | Flask / アプリ共通設定 | `ApplicationSettings`、`webapp.config` | Flask 設定値や外部サービス接続などのキー値ペア |
| `app.cors` | CORS 許可リスト | `ApplicationSettings.get_allowed_origins()` | 許可オリジンの配列を保持 |

> **補足**: 新しい設定を追加する場合は、`SystemSettingService` など読み取り箇所の実装とこのドキュメントを同時に更新してください。

## 3. JSON 構造の詳細

### 3.1 `access_token_signing`

アクセストークンの署名方式を切り替える設定です。構造は次のとおりです。

```json
{
  "mode": "builtin",
  "kid": null,
  "groupCode": null
}
```

| プロパティ | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `mode` | string | 必須 | `"builtin"`（アプリ内蔵鍵）または `"server_signing"`（証明書を利用） |
| `kid` | string \| null | 任意 | `server_signing` モード時の既定証明書 Key ID。空の場合は `groupCode` を使用 |
| `groupCode` | string \| null | `server_signing` では必須 | 利用する証明書グループコード |

- `mode="builtin"` の場合は `kid`・`groupCode` を設定しないでください。
- `mode="server_signing"` かつ `groupCode` が欠けていると、更新時に `AccessTokenSigningValidationError` が送出されます。

#### JSON 例

```json
{
  "mode": "server_signing",
  "groupCode": "prod-signers"
}
```

最新のサーバー署名証明書が自動で選択されます。明示的に `kid` を指定すると、その証明書が優先されます。

### 3.2 `app.config`

Flask の挙動や外部サービス連携など、多用途な設定をまとめます。以下のカテゴリを想定しています。

| カテゴリ | 主なキー | 説明 |
| --- | --- | --- |
| Flask 基本 | `SECRET_KEY`, `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`, `PERMANENT_SESSION_LIFETIME`, `PREFERRED_URL_SCHEME` | セッション・Cookie・URL の初期値 |
| JWT | `JWT_SECRET_KEY`, `ACCESS_TOKEN_ISSUER`, `ACCESS_TOKEN_AUDIENCE` | アクセストークン発行に利用 |
| 国際化 | `LANGUAGES`, `BABEL_DEFAULT_LOCALE`, `BABEL_DEFAULT_TIMEZONE` | 対応言語とタイムゾーン |
| 外部サービス | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `DASHBOARD_DB_URI` など | API 資格情報や接続 URL |
| ファイル・ストレージ | `UPLOAD_TMP_DIR`, `UPLOAD_DESTINATION_DIR`, `UPLOAD_MAX_SIZE`, `FPV_*` 系キー | アップロード制限・保存先 |
| その他 | `CERTS_API_TIMEOUT`, `SERVICE_ACCOUNT_SIGNING_AUDIENCE`, `TRANSCODE_CRF` など | ドメイン固有の調整値 |

#### JSON 例

```json
{
  "SECRET_KEY": "dev-secret-key",
  "SESSION_COOKIE_SECURE": false,
  "LANGUAGES": ["ja", "en"],
  "UPLOAD_MAX_SIZE": 104857600
}
```

- 省略されたキーは `core.system_settings_defaults.DEFAULT_APPLICATION_SETTINGS` の既定値が適用されます。
- 数値は単位（例: バイト）を明示して設定してください。

### 3.3 `app.cors`

CORS ポリシーで許可するオリジンの一覧です。

```json
{
  "allowedOrigins": [
    "https://example.com",
    "https://admin.example.com"
  ]
}
```

| プロパティ | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `allowedOrigins` | array(string) | 必須 | 許可するオリジンの完全 URL。空配列なら全拒否、`"*"` を含めると全許可 |

- スキーム（`https://` 等）を含めた完全な URL で登録してください。
- 環境ごとにオリジンが異なる場合は、該当環境のレコードを直接更新します。

## 4. JSON 管理ポリシー

- アプリケーションは表に記載したプロパティのみを参照します。未知のプロパティが含まれていても DB には保存されますが、**アプリ側では完全に無視** されます。
- 不要なプロパティを追加すると設定の読み手が混乱しやすくなるため、基本的には定義済みの項目だけで構成してください。
- JSON 内の独自メタ情報（例: `"最終更新日"`, `"更新者"`）は利用されません。同等の情報はテーブル列 (`updated_at`) や監査ログで管理する運用を推奨します。
- どうしても追加項目が必要な場合は、アプリケーション側で参照する実装と本ドキュメントを更新してから投入してください。

## 5. 運用・更新手順

1. **初期投入** — `scripts/bootstrap_system_settings.py` が環境変数と既定値からレコードを作成します。
2. **更新** — 管理ツールまたは SQL で JSON を更新すると即時反映され、アプリの再起動は不要です。
3. **環境変数との併用** — DB 接続文字列など秘匿性の高い値は引き続き環境変数で管理してください。

## 6. よくある質問 (FAQ)

### Q1. `setting_key` が `access_token_signing` / `app.config` / `app.cors` だけなのはなぜ？

A. 現時点でアプリケーションが参照する永続設定がこの 3 種類だからです。用途に応じてプレフィックスでグルーピングしており、新しいキーを追加する際は命名規則を崩さないようにしてください。

### Q2. JSON に余計な項目を入れても良いですか？

A. 保存自体は可能ですが、アプリケーションは定義済みのプロパティしか読みません。運用メンバーの混乱を避けるため、不要な項目は追加しない運用を推奨します。

### Q3. すべての JSON に `最終更新日` や `更新者` を入れて統一できますか？

A. 推奨しません。`updated_at` 列で最終更新日時が自動管理されており、更新者はアプリの監査ログで追跡してください。JSON に同様の情報を追加してもアプリは利用せず、手入力による齟齬が発生しやすくなります。

---

このドキュメントはシステム設定を追加・変更するたびに更新してください。疑問点がある場合は開発チームへ確認し、運用ルールと整合性を保つようにしてください。
