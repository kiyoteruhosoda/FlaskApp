# システム設定仕様書

`system_settings` テーブルで管理する永続設定のキーと JSON 構造をまとめた設計ドキュメントです。アプリケーションはここで定義したキーのみを参照し、それ以外の値は利用しません。運用時は DB 内の JSON を直接編集するか、初期投入スクリプトを用いて更新します。

## 1. テーブル概要

| 項目 | 内容 |
| --- | --- |
| テーブル名 | `system_settings` |
| 主キー | `id` (AUTO_INCREMENT) |
| 論理キー | `setting_key`（ユニーク） |
| 値の形式 | `setting_json` 列に JSON として保存 |
| 更新日時 | `updated_at`（自動更新） |

## 2. 設定キー一覧

現在サポートしている `setting_key` は下表の 3 種類です。

| setting_key | 用途 | 主な利用箇所 | JSON 概要 |
| --- | --- | --- | --- |
| `access_token_signing` | アクセストークンの署名方式と証明書の選択 | `SystemSettingService.get_access_token_signing_setting()` | `mode` と証明書識別子を保持 |
| `app.config` | Flask / アプリ共通設定 | `ApplicationSettings`、`webapp.config` | Flask 設定・アップロード制限などのキー値ペア |
| `app.cors` | CORS の許可オリジン | `ApplicationSettings.get_allowed_origins()` | `allowedOrigins` 配列で許可リストを指定 |

> **補足**: 将来的にキーを追加する場合は、アプリケーションコードとこのドキュメントを同時に更新してください。

## 3. 各設定キーの仕様

### 3.1 `access_token_signing`

アクセストークン署名の挙動を制御します。

```json
{
  "mode": "builtin",
  "kid": null,
  "groupCode": null
}
```

| プロパティ | 型 | 必須 | 説明 |
| --- | --- | --- | --- |
| `mode` | string | 必須 | `"builtin"`（アプリ内蔵鍵）または `"server_signing"`（証明書利用） |
| `kid` | string \| null | 任意 | `server_signing` モードの既定証明書 Key ID。空の場合は `groupCode` から自動検索 |
| `groupCode` | string \| null | `server_signing` では必須 | 証明書グループコード |

- `mode="builtin"` の場合は追加項目を設定しないでください。
- `mode="server_signing"` の場合、`groupCode` が未設定だとアプリケーションがエラーを返します。

#### JSON 例

```json
{
  "mode": "server_signing",
  "groupCode": "prod-signers"
}
```

上記のように `groupCode` のみを指定すると、最新のサーバー署名証明書が自動的に選択されます。

### 3.2 `app.config`

Flask 設定やアップロード関連、OAuth 連携など幅広い構成値を管理します。各キーはアプリケーション内で直接参照されます。

| カテゴリ | 主なキー | 説明 |
| --- | --- | --- |
| Flask 基本設定 | `SECRET_KEY`, `SESSION_COOKIE_SECURE`, `SESSION_COOKIE_HTTPONLY`, `SESSION_COOKIE_SAMESITE`, `PERMANENT_SESSION_LIFETIME`, `PREFERRED_URL_SCHEME` | Flask アプリの挙動を制御 |
| JWT | `JWT_SECRET_KEY`, `ACCESS_TOKEN_ISSUER`, `ACCESS_TOKEN_AUDIENCE` | アクセストークン生成パラメータ |
| 国際化 | `LANGUAGES`, `BABEL_DEFAULT_LOCALE`, `BABEL_DEFAULT_TIMEZONE` | 利用可能言語と既定タイムゾーン |
| 外部サービス | `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `DASHBOARD_DB_URI` など | 外部連携の資格情報・接続先 |
| ファイル・ストレージ | `UPLOAD_TMP_DIR`, `UPLOAD_DESTINATION_DIR`, `UPLOAD_MAX_SIZE`, `FPV_*` 系キー | アップロードや CDN 連携設定 |
| その他 | `CERTS_API_TIMEOUT`, `SERVICE_ACCOUNT_SIGNING_AUDIENCE`, `TRANSCODE_CRF` など | ユースケース固有の調整値 |

#### JSON 例

```json
{
  "SECRET_KEY": "dev-secret-key",
  "SESSION_COOKIE_SECURE": false,
  "LANGUAGES": ["ja", "en"],
  "UPLOAD_MAX_SIZE": 104857600
}
```

- 省略されたキーはアプリ側で既定値（`core.system_settings_defaults.DEFAULT_APPLICATION_SETTINGS`）を使用します。
- `UPLOAD_MAX_SIZE` など数値を設定する場合は単位（バイト）に注意してください。

### 3.3 `app.cors`

CORS ポリシーで許可するオリジンを定義します。

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
| `allowedOrigins` | array(string) | 必須 | 許可したいオリジン一覧。空配列の場合はすべて拒否、`"*"` を含めると全許可 |

- 文字列にはスキーム（`https://` 等）を含めてください。
- 運用で複数環境を切り替える場合は、環境ごとに JSON を更新します。

## 4. JSON バリデーション方針

- アプリケーションは上記のキーとプロパティを利用します。未知のプロパティが含まれていても保存自体は可能ですが、**アプリ側では参照されず無視** されます。
- 過剰なプロパティを追加すると管理者が値の意味を誤解する恐れがあるため、原則として本書に記載した構造に従うことを推奨します。
- バリデーションが必要な値（例：`access_token_signing` の `mode`）は `SystemSettingService` 内で検証され、条件を満たさない場合は更新処理で例外が発生します。

## 5. 運用と初期化

1. **初期投入**: `scripts/bootstrap_system_settings.py` を利用すると、環境変数と既定値から初期データを挿入できます。
2. **更新**: 管理ツールや SQL から JSON を更新した後、アプリケーション再起動は不要です（設定は読み込み時に参照されます）。
3. **環境変数との併用**: DB 接続文字列など、セキュアな値の一部は引き続き環境変数で管理してください。

---

このドキュメントはシステム設定の追加・変更時に随時更新してください。疑問点がある場合は開発チームに確認のうえ、運用ルールとの整合性を確保します。
