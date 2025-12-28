"""既存コードと新構造の統合アダプター.

このモジュールは既存のインターフェースを維持しながら、
新しいDDD構造を利用するためのアダプター層を提供します。

段階的移行戦略：
1. 既存の関数シグネチャを維持
2. 内部実装を新構造に委譲
3. 下位互換性を保証
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional, Any, Dict

from core.db import db
from core.models.photo_models import Media
from features.photonest.domain.local_import.value_objects import FileHash
from features.photonest.domain.local_import.services import (
    MediaDuplicateChecker,
    MediaSignature,
)
from features.photonest.infrastructure.local_import import MediaRepositoryImpl


# ===== アダプター層：既存インターフェースを維持 =====


def create_media_signature_from_analysis(analysis) -> MediaSignature:
    """MediaFileAnalysisからMediaSignatureを生成するアダプター.
    
    Args:
        analysis: MediaFileAnalysis オブジェクト
        
    Returns:
        MediaSignature
    """
    file_hash = FileHash(
        sha256=analysis.file_hash,
        size_bytes=analysis.file_size,
        perceptual_hash=analysis.perceptual_hash,
    )
    
    return MediaSignature(
        file_hash=file_hash,
        shot_at=analysis.shot_at,
        width=analysis.width,
        height=analysis.height,
        duration_ms=analysis.duration_ms,
        is_video=analysis.is_video,
    )


def check_duplicate_media_new(analysis) -> Optional[Media]:
    """新構造を使った重複チェック（既存インターフェース維持）.
    
    このアダプター関数は既存の`check_duplicate_media`と同じインターフェースを持ち、
    内部で新しいDDD構造を利用します。
    
    Args:
        analysis: MediaFileAnalysis オブジェクト
        
    Returns:
        重複メディアが見つかればMediaオブジェクト、なければNone
    """
    # 1. MediaFileAnalysis から MediaSignature に変換
    signature = create_media_signature_from_analysis(analysis)
    
    # 2. 新構造のリポジトリとドメインサービスを利用
    repository = MediaRepositoryImpl(db)
    
    # 3. 重複チェック実行
    return repository.find_by_signature(signature)


def check_duplicate_media_with_domain_service(analysis) -> Optional[Media]:
    """ドメインサービスを使った重複チェック（フル新構造版）.
    
    この関数は完全に新しいDDD構造を利用します。
    将来的にはこちらが標準になります。
    
    Args:
        analysis: MediaFileAnalysis オブジェクト
        
    Returns:
        重複メディアが見つかればMediaオブジェクト、なければNone
    """
    # 1. MediaFileAnalysis から MediaSignature に変換
    signature = create_media_signature_from_analysis(analysis)
    
    # 2. リポジトリで候補を取得
    repository = MediaRepositoryImpl(db)
    candidates = repository.find_candidates_by_metadata(
        is_video=signature.is_video,
        shot_at=signature.shot_at,
        width=signature.width,
        height=signature.height,
        duration_ms=signature.duration_ms,
    )
    
    # 3. ドメインサービスで重複判定
    duplicate_checker = MediaDuplicateChecker()
    return duplicate_checker.find_duplicate(signature, candidates)


# ===== ファクトリ関数：使用する実装を切り替え =====


_USE_NEW_DUPLICATE_CHECKER = True  # フィーチャーフラグ


def check_duplicate_media_auto(analysis) -> Optional[Media]:
    """自動切り替え：環境に応じて新旧実装を選択.
    
    フィーチャーフラグにより、新旧実装を切り替えます。
    これにより、問題が発生した場合に即座にロールバック可能です。
    
    Args:
        analysis: MediaFileAnalysis オブジェクト
        
    Returns:
        重複メディアが見つかればMediaオブジェクト、なければNone
    """
    if _USE_NEW_DUPLICATE_CHECKER:
        try:
            return check_duplicate_media_new(analysis)
        except Exception:
            # 新実装で失敗した場合は旧実装にフォールバック
            from core.tasks.local_import import check_duplicate_media as old_check
            return old_check(analysis)
    else:
        from core.tasks.local_import import check_duplicate_media as old_check
        return old_check(analysis)


# ===== パフォーマンス比較ユーティリティ =====


def compare_duplicate_checkers(analysis) -> Dict[str, Any]:
    """新旧実装のパフォーマンスと結果を比較.
    
    テスト・デバッグ用の関数です。
    新旧実装の実行時間と結果の一致を確認します。
    
    Args:
        analysis: MediaFileAnalysis オブジェクト
        
    Returns:
        比較結果の辞書
    """
    import time
    from core.tasks.local_import import check_duplicate_media as old_check
    
    # 旧実装の実行
    start_old = time.perf_counter()
    result_old = old_check(analysis)
    time_old = time.perf_counter() - start_old
    
    # 新実装の実行
    start_new = time.perf_counter()
    result_new = check_duplicate_media_new(analysis)
    time_new = time.perf_counter() - start_new
    
    # 結果の比較
    match = (result_old is None and result_new is None) or (
        result_old is not None
        and result_new is not None
        and result_old.id == result_new.id
    )
    
    return {
        "match": match,
        "old_result_id": result_old.id if result_old else None,
        "new_result_id": result_new.id if result_new else None,
        "old_time_ms": time_old * 1000,
        "new_time_ms": time_new * 1000,
        "speedup": time_old / time_new if time_new > 0 else None,
    }
