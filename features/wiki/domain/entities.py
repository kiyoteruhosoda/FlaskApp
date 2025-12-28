"""
Wiki domain entities - 純粋な業務ロジックとドメインモデル
"""

from datetime import datetime
from typing import Optional, List
from dataclasses import dataclass


@dataclass
class WikiPage:
    """Wikiページのドメインエンティティ"""
    id: Optional[int]
    title: str
    content: str
    slug: str
    created_at: Optional[datetime]
    updated_at: Optional[datetime]
    created_by_id: int
    updated_by_id: Optional[int]
    is_published: bool = True
    parent_id: Optional[int] = None
    sort_order: int = 0
    
    def __post_init__(self):
        if self.updated_by_id is None:
            self.updated_by_id = self.created_by_id
    
    def is_valid(self) -> bool:
        """ドメインルールの検証"""
        return (
            bool(self.title.strip()) and 
            bool(self.slug.strip()) and 
            self.created_by_id > 0
        )
    
    def can_be_edited_by(self, user_id: int) -> bool:
        """編集権限の確認（ドメインルール）"""
        # 作成者は常に編集可能
        return self.created_by_id == user_id


@dataclass 
class WikiCategory:
    """Wikiカテゴリのドメインエンティティ"""
    id: Optional[int]
    name: str
    description: Optional[str]
    slug: str
    created_at: Optional[datetime]
    sort_order: int = 0
    
    def is_valid(self) -> bool:
        """ドメインルールの検証"""
        return bool(self.name.strip()) and bool(self.slug.strip())


@dataclass
class WikiRevision:
    """Wikiページの履歴管理"""
    id: Optional[int]
    page_id: int
    title: str
    content: str
    created_at: Optional[datetime]
    created_by_id: int
    revision_number: int
    change_summary: Optional[str] = None
