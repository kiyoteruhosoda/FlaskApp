"""Slug に関するドメインサービスおよび値オブジェクト。"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Slug:
    """Wiki ドメインで利用するスラッグを表す値オブジェクト。"""

    value: str

    def __post_init__(self) -> None:
        normalized = (self.value or "").strip()
        if not normalized:
            raise ValueError("slug value must not be empty")
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:  # pragma: no cover - dataclass repr helper
        return self.value


class SlugNormalizer:
    """テキストからスラッグ文字列を生成する正規化コンポーネント。"""

    _INVALID_PATTERN = re.compile(r"[^\w\s-]", re.UNICODE)
    _HYPHEN_PATTERN = re.compile(r"[-\s]+")

    def normalize(self, text: str) -> str:
        if not text:
            return ""

        normalized = unicodedata.normalize("NFKC", text)
        normalized = normalized.lower()
        normalized = self._INVALID_PATTERN.sub("", normalized)
        normalized = self._HYPHEN_PATTERN.sub("-", normalized)
        return normalized.strip("-")


class SlugService:
    """スラッグに関するドメインサービス。"""

    _VALID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")

    def __init__(self, normalizer: SlugNormalizer | None = None) -> None:
        self._normalizer = normalizer or SlugNormalizer()

    def generate_from_text(self, text: str) -> Slug:
        """任意のテキストからスラッグを生成する。"""

        normalized = self._normalizer.normalize(text)
        if not normalized:
            raise ValueError("normalized slug must not be empty")
        return Slug(normalized)

    def from_user_input(self, slug: str) -> Slug:
        """ユーザー入力済みのスラッグから値オブジェクトを生成する。"""

        candidate = (slug or "").strip()
        if not candidate:
            raise ValueError("slug must not be blank")
        if not self.is_valid(candidate):
            raise ValueError("slug contains invalid characters")
        return Slug(candidate)

    def ensure_unique(self, slug: Slug, exists: Callable[[str], bool]) -> Slug:
        """既存スラッグと重複しないように調整する。"""

        if not exists(slug.value):
            return slug

        base_value = slug.value
        counter = 1
        while True:
            candidate_value = f"{base_value}-{counter}"
            if not exists(candidate_value):
                return Slug(candidate_value)
            counter += 1

    def generate_unique_from_text(self, text: str, exists: Callable[[str], bool]) -> Slug:
        """テキストから生成したスラッグに重複対策を施す。"""

        return self.ensure_unique(self.generate_from_text(text), exists)

    @staticmethod
    def is_valid(slug: str) -> bool:
        if not slug:
            return False
        return bool(SlugService._VALID_PATTERN.match(slug))
