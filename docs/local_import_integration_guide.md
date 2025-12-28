# Local Import 統合ガイド

## 概要

このガイドは、既存のlocal import処理と新しいDDD構造を統合する方法を説明します。
**段階的な移行**により、下位互換性を保ちながら安全に新構造を導入します。

---

## 統合完了の状態

### ✅ 完了した作業

1. **アダプター層の作成**
   - `features/photonest/application/local_import/adapters.py`
   - 既存インターフェースを維持したまま新構造を利用
   - フィーチャーフラグによる新旧切り替え機能

2. **既存コードの修正**
   - `core/tasks/local_import.py`の`check_duplicate_media()`を更新
   - 新実装を使用し、エラー時は自動的に旧実装にフォールバック

3. **テストヘルパーの作成**
   - `tests/helpers/local_import_test_helpers.py`
   - ビルダーパターンによるテストデータ作成
   - 新旧実装の比較ユーティリティ

4. **ユニットテストの作成**
   - `tests/test_local_import_new_structure.py`
   - 値オブジェクト・ドメインサービスの単体テスト

---

## 使用方法

### 1. 通常使用（自動切り替え）

既存のコードはそのまま動作します。内部で自動的に新構造を使用します：

```python
from core.tasks.local_import import check_duplicate_media

# 既存のインターフェースのまま使用可能
analysis = MediaFileAnalysis(...)
duplicate = check_duplicate_media(analysis)
```

### 2. 新構造を直接使用

新しいコードでは、直接新構造を利用できます：

```python
from features.photonest.domain.local_import.services import (
    MediaDuplicateChecker,
    MediaSignature,
)
from features.photonest.domain.local_import.value_objects import FileHash
from features.photonest.infrastructure.local_import import MediaRepositoryImpl

# MediaSignatureを作成
file_hash = FileHash(
    sha256="abc...",
    size_bytes=1024,
    perceptual_hash="phash123",
)
signature = MediaSignature(
    file_hash=file_hash,
    shot_at=datetime.now(timezone.utc),
    width=1920,
    height=1080,
    duration_ms=None,
    is_video=False,
)

# リポジトリとドメインサービスを使用
repository = MediaRepositoryImpl(db)
candidates = repository.find_candidates_by_metadata(...)
checker = MediaDuplicateChecker()
duplicate = checker.find_duplicate(signature, candidates)
```

### 3. テストでの使用

テストヘルパーを使用すると簡単にテストデータを作成できます：

```python
from tests.helpers.local_import_test_helpers import (
    MediaSignatureBuilder,
    MockMedia,
    create_test_signature,
)

# ビルダーパターンでテストデータ作成
signature = MediaSignatureBuilder() \
    .with_hash("abc" + "0" * 61, 1024, "phash123") \
    .with_metadata(datetime.now(), 1920, 1080) \
    .as_image() \
    .build()

# またはショートカット
signature = create_test_signature(hash_value="abc...", phash="phash123")

# モックMediaの作成
mock_media = MockMedia(
    id=1,
    hash_sha256="abc...",
    bytes=1024,
    phash="phash123",
)
```

---

## フィーチャーフラグ

新旧実装の切り替えはフィーチャーフラグで制御されます：

```python
from features.photonest.application.local_import import adapters

# 新実装を有効化（デフォルト）
adapters._USE_NEW_DUPLICATE_CHECKER = True

# 旧実装に戻す（問題発生時）
adapters._USE_NEW_DUPLICATE_CHECKER = False
```

本番環境で問題が発生した場合、このフラグを変更するだけで即座にロールバック可能です。

---

## エラーハンドリング

新実装で例外が発生した場合、自動的に旧実装にフォールバックします：

```python
def check_duplicate_media(analysis):
    try:
        return check_duplicate_media_new(analysis)
    except Exception as exc:
        # 警告ログを出力
        _log_warning("local_import.duplicate_check.fallback", ...)
        
        # 旧実装で処理続行
        return old_implementation(analysis)
```

これにより、新実装にバグがあっても処理は継続されます。

---

## パフォーマンスモニタリング

新旧実装のパフォーマンスを比較できます：

```python
from features.photonest.application.local_import.adapters import (
    compare_duplicate_checkers,
)

analysis = MediaFileAnalysis(...)
comparison = compare_duplicate_checkers(analysis)

print(f"Results match: {comparison['match']}")
print(f"Old implementation: {comparison['old_time_ms']:.2f}ms")
print(f"New implementation: {comparison['new_time_ms']:.2f}ms")
print(f"Speedup: {comparison['speedup']:.2f}x")
```

---

## テスト実行

### 新構造のユニットテスト

```bash
# 仮想環境をアクティベート
source /home/kyon/myproject/.venv/bin/activate

# 新構造のテストのみ実行
pytest tests/test_local_import_new_structure.py -v

# カバレッジ付き実行
pytest tests/test_local_import_new_structure.py --cov=features.photonest.domain.local_import --cov-report=html
```

### 既存テストとの互換性確認

```bash
# local_import関連の全テスト実行
pytest tests/test_local_import.py tests/test_local_import_ui.py -v

# 新旧実装の比較テスト
pytest tests/test_local_import.py::test_check_duplicate_media -v
```

---

## トラブルシューティング

### 問題：新実装でエラーが頻発する

**原因**：新構造にバグがある可能性  
**対処**：フィーチャーフラグで旧実装に戻す

```python
from features.photonest.application.local_import import adapters
adapters._USE_NEW_DUPLICATE_CHECKER = False
```

### 問題：新旧実装で結果が異なる

**原因**：ビジネスロジックの実装差異  
**対処**：比較ユーティリティで調査

```python
from features.photonest.application.local_import.adapters import (
    compare_duplicate_checkers,
)

# 問題のあるanalysisで比較
comparison = compare_duplicate_checkers(analysis)
if not comparison['match']:
    print(f"Old result: {comparison['old_result_id']}")
    print(f"New result: {comparison['new_result_id']}")
    # 詳細調査...
```

### 問題：テストが失敗する

**原因**：テストが旧実装に依存している  
**対処**：テストで明示的に旧実装を使用

```python
from tests.helpers.local_import_test_helpers import (
    disable_new_duplicate_checker,
)

def test_with_old_implementation():
    disable_new_duplicate_checker()
    # テスト実行...
```

---

## 次のステップ

### 短期（1-2週間）

1. ✅ 新構造の基本動作確認
2. ⏳ 既存テストの全件実行と修正
3. ⏳ パフォーマンステストの実施
4. ⏳ エラーログのモニタリング

### 中期（1ヶ月）

1. ⏳ 他の関数（`_refresh_existing_media_metadata`など）の移行
2. ⏳ ファイル処理全体を新構造に移行
3. ⏳ トランザクション管理の統合

### 長期（2-3ヶ月）

1. ⏳ 旧実装の完全削除
2. ⏳ ドキュメントの更新
3. ⏳ 他モジュールへのDDD適用

---

## チェックリスト

### デプロイ前

- [ ] 全ユニットテストが通る
- [ ] 既存の統合テストが通る
- [ ] パフォーマンステストで劣化なし
- [ ] フィーチャーフラグが正しく動作
- [ ] ロールバック手順が明確

### デプロイ後

- [ ] エラーログを監視（24時間）
- [ ] パフォーマンスメトリクスを監視
- [ ] 新旧実装の結果一致率を確認
- [ ] ユーザーからの問題報告なし

### 完全移行前

- [ ] 新実装が2週間安定稼働
- [ ] 全ケースで新旧結果が一致
- [ ] コードレビュー完了
- [ ] ドキュメント更新完了

---

## よくある質問

### Q: 既存のコードを変更する必要はありますか？

A: **いいえ**、既存のコードはそのまま動作します。内部実装が自動的に新構造を使用します。

### Q: テストも変更が必要ですか？

A: 多くの場合、**変更不要**です。ただし、内部実装の詳細に依存するテストは修正が必要な場合があります。

### Q: パフォーマンスへの影響は？

A: 新構造は最適化されており、同等以上のパフォーマンスが期待できます。比較ユーティリティで実測できます。

### Q: 問題が発生したらどうすればいい？

A: フィーチャーフラグで即座に旧実装に戻せます。また、新実装で例外が発生した場合は自動的にフォールバックします。

### Q: いつ旧実装を削除できますか？

A: 新実装が2週間以上安定稼働し、全テストが通り、パフォーマンスも問題ない場合に削除を検討できます。

---

## 関連ドキュメント

- [local_import_refactoring.md](local_import_refactoring.md) - リファクタリング設計書
- [AGENTS.md](../AGENTS.md) - プロジェクト共通ルール
- [requirements.md](../requirements.md) - システム要件定義

---

## 連絡先

問題や質問があれば、以下で報告してください：

- Issue トラッカー
- プロジェクトチャンネル
- コードレビュー時
