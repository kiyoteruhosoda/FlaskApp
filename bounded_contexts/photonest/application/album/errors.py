"""Album ユースケースの失敗を表現するアプリケーション例外.

Presentation 層へは「安定したエラーコード」「英語メッセージキー」「HTTP ステータス」
「追加詳細」のみを伝える。実際の翻訳（``_()``）と JSON 整形は Presentation 層が行う。
"""
from __future__ import annotations

from typing import Any, Mapping


class AlbumApplicationError(Exception):
    """ユースケースが入力やリソース状態を理由に処理を続行できない場合に送出する.

    Attributes:
        code: レスポンスの ``error`` フィールドに使う安定識別子。
        message: 翻訳キーとして使う英語メッセージ。
        status: HTTP ステータスコード。
        details: レスポンスへ追加マージする情報（例: ``missingMediaIds``）。
    """

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status: int = 400,
        details: Mapping[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details: dict[str, Any] = dict(details or {})

    # --- ファクトリ（メッセージを一元管理し、ルート間で文言を一致させる） ---

    @classmethod
    def name_required(cls) -> "AlbumApplicationError":
        return cls("name_required", "Album name is required.")

    @classmethod
    def invalid_visibility(cls) -> "AlbumApplicationError":
        return cls("invalid_visibility", "Invalid album visibility value.")

    @classmethod
    def invalid_media_ids(cls) -> "AlbumApplicationError":
        return cls("invalid_media_ids", "Invalid media selection payload.")

    @classmethod
    def cover_not_integer(cls) -> "AlbumApplicationError":
        return cls("invalid_cover", "Cover media id must be an integer.")

    @classmethod
    def cover_not_in_selection(cls) -> "AlbumApplicationError":
        return cls(
            "invalid_cover",
            "Cover image must be one of the selected media items.",
        )

    @classmethod
    def media_not_found(cls, missing_media_ids: list[int]) -> "AlbumApplicationError":
        return cls(
            "invalid_media",
            "Some selected media could not be found.",
            details={"missingMediaIds": missing_media_ids},
        )

    @classmethod
    def album_not_found(cls) -> "AlbumApplicationError":
        return cls("not_found", "Album not found.", status=404)

    @classmethod
    def media_order_not_list(cls) -> "AlbumApplicationError":
        return cls(
            "invalid_media_order",
            "Media order payload must be a list of media ids.",
        )

    @classmethod
    def media_order_not_unique(cls) -> "AlbumApplicationError":
        return cls(
            "invalid_media_order",
            "Media order payload must include each album media id exactly once.",
        )

    @classmethod
    def media_order_mismatch(cls) -> "AlbumApplicationError":
        return cls(
            "invalid_media_order",
            "Media order payload must include every media id currently in the album.",
        )

    @classmethod
    def album_order_empty(cls) -> "AlbumApplicationError":
        return cls(
            "invalid_payload",
            "Album order payload must include at least one album id.",
        )

    @classmethod
    def album_order_not_integer(cls) -> "AlbumApplicationError":
        return cls(
            "invalid_payload",
            "Album order payload must include integer ids.",
        )

    @classmethod
    def albums_not_found(cls, missing_album_ids: list[int]) -> "AlbumApplicationError":
        return cls(
            "invalid_album",
            "Some specified albums could not be found.",
            details={"missingAlbumIds": missing_album_ids},
        )


__all__ = ["AlbumApplicationError"]
