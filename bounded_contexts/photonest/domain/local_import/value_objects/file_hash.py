"""ファイルハッシュ値オブジェクト."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class FileHash:
    """ファイルのハッシュ値を表す値オブジェクト.
    
    不変であり、値による等価性を持つ。
    """
    
    sha256: str
    size_bytes: int
    perceptual_hash: Optional[str] = None
    
    def __post_init__(self) -> None:
        """バリデーション."""
        if not self.sha256 or len(self.sha256) != 64:
            raise ValueError(f"Invalid SHA-256 hash: {self.sha256}")
        if not isinstance(self.sha256, str) or not all(c in '0123456789abcdef' for c in self.sha256.lower()):
            raise ValueError(f"SHA-256 hash must be hexadecimal: {self.sha256}")
        if self.size_bytes < 0:
            raise ValueError(f"File size cannot be negative: {self.size_bytes}")
        if self.perceptual_hash is not None and not self.perceptual_hash:
            # 空文字列はNoneに正規化
            object.__setattr__(self, 'perceptual_hash', None)
    
    def matches_cryptographic(self, other: FileHash) -> bool:
        """暗号学的ハッシュ（SHA-256 + サイズ）による一致判定."""
        return (
            self.sha256 == other.sha256
            and self.size_bytes == other.size_bytes
        )
    
    def matches_perceptual(self, other: FileHash) -> bool:
        """知覚的ハッシュ（pHash）による一致判定."""
        if not self.perceptual_hash or not other.perceptual_hash:
            return False
        return self.perceptual_hash == other.perceptual_hash
