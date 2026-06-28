"""既存コードと新構造の統合アダプター.

このモジュールは既存のインターフェースを維持しながら、
新しいDDD構造を利用するためのアダプター層を提供します。

段階的移行戦略：
1. 既存の関数シグネチャを維持
2. 内部実装を新構造に委譲
3. 下位互換性を保証
"""
from __future__ import annotations
from typing import Optional

from shared.kernel.database.db import db
from bounded_contexts.photonest.infrastructure.photo_models import Media
from bounded_contexts.photonest.domain.local_import.value_objects import FileHash
from bounded_contexts.photonest.domain.local_import.services import (
    MediaDuplicateChecker,
    MediaSignature,
)
from bounded_contexts.photonest.infrastructure.local_import import MediaRepositoryImpl


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
    """ドメインサービスを使った重複チェック（候補取得＋ドメイン判定の別経路）.

    ``check_duplicate_media_new`` がリポジトリ内でクエリ最適化して判定するのに対し、
    こちらは候補をメタデータで取得してから ``MediaDuplicateChecker`` で判定する。
    ドメインサービス単体の利用例として残す（標準経路は ``check_duplicate_media_new``）。

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
