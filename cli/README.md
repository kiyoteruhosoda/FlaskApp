# PhotoNest CLI (`fpv`)

Minimal CLI skeleton. `fpv --help` shows the help screen and subcommand usage.

## Install (editable)

```bash
cd cli
python -m pip install -e .
```

## Sync (dry-run outline)

First apply the DDL and check configuration:

```bash
fpv config check
```

Run dry-run (records job history and outputs structured logs):

```bash
fpv sync --dry-run
# Single account only:
# fpv sync --single-account --account-id 1 --dry-run
```

`--no-dry-run` will be effective in later steps when the actual API implementation is added.

## Google API 疎通（1ページだけ）

1) 事前に DB へ `google_account` を1件投入（開発初期は **平文JSON** でも可）:

```sql
INSERT INTO google_account (account_email, oauth_token_json, status)
VALUES (
  'you@example.com',
  '{"refresh_token":"<実際のRefreshToken>"}',
  'active'
);
```

> 本番は `oauth_token_json` を AES-GCM で暗号化したエンベロープにしてください（CLIはどちらも解釈可能）。

2. `.env` に Google クレデンシャルを設定:

```
FPV_GOOGLE_CLIENT_ID=...apps.googleusercontent.com
FPV_GOOGLE_CLIENT_SECRET=...
FPV_OAUTH_KEY=base64:<32bytes>   # 平文JSONを使う場合でも設定してOK
```

3. 実行:

```bash
python -m pip install -e .
fpv db up
fpv config check
fpv sync --no-dry-run
```

* 成功すると `sync.token.ok` → `sync.list.ok` のログが出て、`job_sync` は `success`。
* `invalid_grant`（失効/削除）は `sync.account.reauth_required` として `failed` になります。
