# PhotoNest CLI (`fpv`)

最小のCLIスケルトン。`fpv --help` が表示でき、各サブコマンドのヘルプも出ます。

## Install (editable)

```bash
cd cli
python -m pip install -e .
```

## Sync (外形テスト: dry-run)

まずはDDL適用と設定チェック:

```bash
fpv config check
```

dry-run 実行（ジョブ履歴が記録され、構造化ログが出ます）:

```bash
fpv sync --dry-run
# 単一IDのみ:
# fpv sync --single-account --account-id 1 --dry-run
```

`--no-dry-run` は次ステップ以降（実API実装）で有効になります。
