"""バリデーションユーティリティ"""
from __future__ import annotations

import base64
import re
from typing import Tuple

from .exceptions import TOTPValidationError

_ALLOWED_ALGORITHMS = {"SHA1", "SHA256", "SHA512"}
_SECRET_CHARS = re.compile(r"^[A-Z2-7]+=*$")


def normalize_secret(secret: str) -> str:
    if not secret:
        raise TOTPValidationError("シークレットを入力してください", field="secret")
    cleaned = re.sub(r"\s+", "", secret).replace("-", "")
    cleaned = cleaned.upper()
    return cleaned


def validate_secret(secret: str) -> str:
    normalized = normalize_secret(secret)
    # Base32 のパディングを自動調整
    padding = len(normalized) % 8
    if padding:
        normalized = normalized + ("=" * (8 - padding))
    if not _SECRET_CHARS.match(normalized):
        raise TOTPValidationError("シークレットは Base32 形式で入力してください", field="secret")
    try:
        base64.b32decode(normalized, casefold=True)
    except Exception as exc:  # noqa: BLE001
        raise TOTPValidationError("シークレットの形式が正しくありません", field="secret") from exc
    return normalized.rstrip("=")


def validate_algorithm(algorithm: str) -> str:
    if not algorithm:
        return "SHA1"
    algorithm = algorithm.upper()
    if algorithm not in _ALLOWED_ALGORITHMS:
        raise TOTPValidationError("利用できないアルゴリズムです", field="algorithm")
    return algorithm


def validate_digits_and_period(digits: int | None, period: int | None) -> Tuple[int, int]:
    digits = digits or 6
    period = period or 30
    if digits < 4 or digits > 10:
        raise TOTPValidationError("桁数は4〜10の範囲で指定してください", field="digits")
    if period < 15 or period > 120:
        raise TOTPValidationError("有効期間は15〜120秒の範囲で指定してください", field="period")
    return digits, period
