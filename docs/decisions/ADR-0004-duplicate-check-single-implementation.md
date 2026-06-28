# ADR-0004: 重複判定を単一実装に統合（サイレントフォールバック廃止）

- ステータス: Accepted
- 日付: 2026-06-28

## コンテキスト

`check_duplicate_media` は新実装 `check_duplicate_media_new`（DDD:
`MediaRepositoryImpl.find_by_signature`）を呼び、**例外時に旧実装へサイレント
フォールバック**していた。旧実装は同等ロジックの二重定義で、`adapters.py` にも
未使用の切替機構（`check_duplicate_media_auto` / `_USE_NEW_DUPLICATE_CHECKER` /
`compare_duplicate_checkers`）が残っていた。

二重実装は (1) 失敗が隠れる、(2) 保守対象が増える、という問題があった。

## 新実装は信頼できるか（検証結果）

- **ロジック等価性**: `find_by_signature` は旧実装と同じ優先順位
  （pHash＋メタデータ → pHash のみ → SHA-256＋サイズ）を保持。差異は動画以外での
  `duration_ms` フィルタ有無のみで、写真は `duration_ms=NULL` のため実質等価。
- **例外経路**: 新実装が旧実装と異なり例外を出す唯一の経路は、署名 `FileHash` の
  検証（SHA-256 が None・長さ≠64・非16進、または負サイズ）。通常の取り込みでは
  `calculate_file_hash` が 64桁hex を返すため発生しない。
- 単体テストで exact(sha256)/similar(phash)/重複なし/不正ハッシュを検証し一致を確認。

→ 通常運用では新実装を全面的に信頼できる、と判断。

## 決定

- `check_duplicate_media` は `check_duplicate_media_new` に委譲する単一実装にする。
- 旧実装ロジックと切替機構（`check_duplicate_media_auto` /
  `_USE_NEW_DUPLICATE_CHECKER` / `compare_duplicate_checkers`）を削除する。
- 例外の握りつぶしをやめ、**唯一の既知エッジ（不正ハッシュ＝`ValueError`）のみ**を
  明示的に捕捉し、警告ログを残して「重複なし」で取り込みを継続する。想定外の例外は
  伝播させ、失敗を隠さない。

## 影響

- 重複判定ロジックが1か所になり保守性が向上。失敗が表面化するようになる。
- 不正ハッシュという異常入力時は重複判定をスキップ（None）して取り込み継続。
- `check_duplicate_media_with_domain_service` はドメインサービス利用例として残置。
