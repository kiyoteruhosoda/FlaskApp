"""相対パスを表す値オブジェクト."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class RelativePath:
    """安全な相対パスを表す値オブジェクト.
    
    パストラバーサル攻撃を防ぐため、".." や絶対パスを拒否する。
    """
    
    value: str
    
    def __post_init__(self) -> None:
        """バリデーション."""
        if not self.value:
            raise ValueError("Relative path cannot be empty")
        
        # パストラバーサル攻撃の防止
        path = Path(self.value)
        if path.is_absolute():
            raise ValueError(f"Path must be relative: {self.value}")
        
        parts = self._normalize_parts(path)
        if any(part == ".." for part in parts):
            raise ValueError(f"Path cannot contain '..': {self.value}")
        
        # 正規化されたパスを再設定
        normalized = "/".join(parts)
        object.__setattr__(self, 'value', normalized)
    
    @staticmethod
    def _normalize_parts(path: Path) -> List[str]:
        """パス要素を正規化."""
        parts: List[str] = []
        for part in path.parts:
            if part in {"", "."}:
                continue
            if part == "..":
                # バリデーションで弾くため、ここには到達しないはず
                continue
            parts.append(part)
        return parts
    
    def join(self, base_dir: str) -> Path:
        """ベースディレクトリと結合して絶対パスを返す."""
        return Path(base_dir) / self.value
    
    def parent(self) -> RelativePath:
        """親ディレクトリの相対パスを返す."""
        parent_path = Path(self.value).parent
        if str(parent_path) == ".":
            raise ValueError("Path has no parent")
        return RelativePath(str(parent_path))
    
    def stem(self) -> str:
        """拡張子を除いたファイル名を返す."""
        return Path(self.value).stem
    
    def suffix(self) -> str:
        """拡張子を返す（ドット付き）."""
        return Path(self.value).suffix
    
    def __str__(self) -> str:
        return self.value
