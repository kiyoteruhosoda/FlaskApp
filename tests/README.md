# テスト実行ガイド

## 概要

このプロジェクトのテストは、外部依存の有無によって分類されています：

- **ユニットテスト** (`@pytest.mark.unit`): 外部依存なし、高速
- **統合テスト** (`@pytest.mark.integration`): データベースや外部サービスに依存
- **外部リソーステスト**: FFmpeg、ファイルシステム、SMTPなどに依存

## デフォルト実行

```bash
# 仮想環境を有効化
source /home/kyon/myproject/.venv/bin/activate

# デフォルト設定でテストを実行（外部依存テストを除外）
pytest
```

デフォルトでは、以下のマーカーが付いたテストは**スキップ**されます：
- `@pytest.mark.ffmpeg`: FFmpegが必要なテスト
- `@pytest.mark.filesystem`: 実ファイルシステムアクセスが必要なテスト
- `@pytest.mark.smtp`: SMTPサーバーが必要なテスト

## テストカテゴリ別実行

### ユニットテストのみ実行

```bash
pytest -m "unit"
```

### 統合テストのみ実行

```bash
pytest -m "integration"
```

### 外部依存テストを含めてすべて実行

```bash
pytest -m ""
```

または、特定のマーカーのみを有効化：

```bash
# FFmpegテストを含む
pytest -m "not (filesystem or smtp)"

# ファイルシステムテストを含む
pytest -m "not (ffmpeg or smtp)"
```

## よく使うオプション

### 高速実行（並列処理）

```bash
pytest -n auto
```

### 詳細出力

```bash
pytest -xvs
```

- `-x`: 最初の失敗で停止
- `-v`: 詳細表示
- `-s`: print出力を表示

### 特定のテストファイルのみ実行

```bash
pytest tests/test_email_integration.py
```

### 特定のテスト関数のみ実行

```bash
pytest tests/test_email_integration.py::test_email_service_with_console_sender
```

## トラブルシューティング

### "外部依存が必要" エラー

外部リソース（FFmpeg、実ファイルシステム等）が必要なテストを実行しようとした場合、該当マーカーを含めて実行してください：

```bash
pytest -m ""  # すべてのテストを実行
```

### テストが遅い

データベース接続の初期化に時間がかかる場合があります。通常、初回実行後はキャッシュが効いて高速化されます。

### タイムアウトエラー

長時間実行されるテストがある場合、pytest-timeoutプラグインを使用してタイムアウトを設定できます：

```bash
pytest --timeout=300  # 5分のタイムアウト
```

## CI/CDでの実行

CI/CD環境では、デフォルト設定（外部依存テストを除外）で実行することを推奨します：

```bash
pytest --tb=short -q
```

統合テスト用の環境が整っている場合は、すべてのテストを実行：

```bash
pytest -m "" --tb=short
```

## テストマーカー一覧

| マーカー | 説明 | デフォルト |
|---------|------|----------|
| `unit` | 外部依存のない高速なユニットテスト | 実行 |
| `integration` | 外部リソース（DB等）を必要とする統合テスト | 実行 |
| `ffmpeg` | FFmpegが必要なテスト | スキップ |
| `filesystem` | 実ファイルシステムアクセスが必要なテスト | スキップ |
| `smtp` | SMTPサーバーが必要なテスト | スキップ |

## マーカーの追加方法

新しいテストファイルにマーカーを追加する場合：

```python
import pytest

# ファイル全体にマーカーを適用
pytestmark = pytest.mark.unit

# または複数のマーカー
pytestmark = [pytest.mark.integration, pytest.mark.filesystem]

def test_something():
    pass
```

個別のテスト関数にマーカーを追加：

```python
@pytest.mark.unit
def test_something():
    pass
```

## 参考

- [pytest documentation](https://docs.pytest.org/)
- [pytest markers](https://docs.pytest.org/en/stable/how-to/mark.html)
