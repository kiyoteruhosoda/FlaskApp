"""メディア一致判定の仕様パターン."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Protocol

from ..services.duplicate_checker import MediaEntity, MediaSignature


class Specification(ABC):
    """仕様パターンの基底クラス."""
    
    @abstractmethod
    def is_satisfied_by(self, candidate: MediaEntity, target: MediaSignature) -> bool:
        """仕様を満たすかどうか."""
        pass
    
    def and_(self, other: Specification) -> Specification:
        """AND結合."""
        return AndSpecification(self, other)
    
    def or_(self, other: Specification) -> Specification:
        """OR結合."""
        return OrSpecification(self, other)
    
    def not_(self) -> Specification:
        """NOT."""
        return NotSpecification(self)


class AndSpecification(Specification):
    """AND仕様."""
    
    def __init__(self, left: Specification, right: Specification) -> None:
        self.left = left
        self.right = right
    
    def is_satisfied_by(self, candidate: MediaEntity, target: MediaSignature) -> bool:
        return (
            self.left.is_satisfied_by(candidate, target)
            and self.right.is_satisfied_by(candidate, target)
        )


class OrSpecification(Specification):
    """OR仕様."""
    
    def __init__(self, left: Specification, right: Specification) -> None:
        self.left = left
        self.right = right
    
    def is_satisfied_by(self, candidate: MediaEntity, target: MediaSignature) -> bool:
        return (
            self.left.is_satisfied_by(candidate, target)
            or self.right.is_satisfied_by(candidate, target)
        )


class NotSpecification(Specification):
    """NOT仕様."""
    
    def __init__(self, spec: Specification) -> None:
        self.spec = spec
    
    def is_satisfied_by(self, candidate: MediaEntity, target: MediaSignature) -> bool:
        return not self.spec.is_satisfied_by(candidate, target)


class NotDeletedSpecification(Specification):
    """削除されていないメディアの仕様."""
    
    def is_satisfied_by(self, candidate: MediaEntity, target: MediaSignature) -> bool:
        return not candidate.is_deleted


class SameVideoTypeSpecification(Specification):
    """同じ動画フラグを持つメディアの仕様."""
    
    def is_satisfied_by(self, candidate: MediaEntity, target: MediaSignature) -> bool:
        return candidate.is_video == target.is_video


class ExactMatchSpecification(Specification):
    """完全一致の仕様（pHash + メタデータ）."""
    
    def is_satisfied_by(self, candidate: MediaEntity, target: MediaSignature) -> bool:
        from ..services.duplicate_checker import MediaDuplicateChecker
        
        candidate_sig = MediaDuplicateChecker._to_signature(candidate)
        return target.matches_exact(candidate_sig)


class PerceptualMatchSpecification(Specification):
    """知覚的一致の仕様（pHashのみ）."""
    
    def is_satisfied_by(self, candidate: MediaEntity, target: MediaSignature) -> bool:
        from ..services.duplicate_checker import MediaDuplicateChecker
        
        candidate_sig = MediaDuplicateChecker._to_signature(candidate)
        return target.matches_perceptual(candidate_sig)


class CryptographicMatchSpecification(Specification):
    """暗号学的一致の仕様（SHA-256 + サイズ）."""
    
    def is_satisfied_by(self, candidate: MediaEntity, target: MediaSignature) -> bool:
        from ..services.duplicate_checker import MediaDuplicateChecker
        
        candidate_sig = MediaDuplicateChecker._to_signature(candidate)
        return target.matches_loose(candidate_sig)
