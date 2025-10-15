"""otpauth URI の解析"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qs, unquote, urlparse

from .exceptions import TOTPValidationError


@dataclass(slots=True)
class OtpauthData:
    account: str
    issuer: str
    secret: str
    description: Optional[str]
    algorithm: str
    digits: int
    period: int


def parse_otpauth_uri(uri: str) -> OtpauthData:
    if not uri:
        raise TOTPValidationError("otpauth URI が空です", field="otpauth_uri")

    parsed = urlparse(uri)
    if parsed.scheme != "otpauth" or parsed.netloc.lower() != "totp":
        raise TOTPValidationError("TOTP 用の otpauth URI ではありません", field="otpauth_uri")

    label = unquote(parsed.path[1:]) if parsed.path.startswith("/") else unquote(parsed.path)
    if not label:
        raise TOTPValidationError("otpauth URI にアカウント名が含まれていません", field="otpauth_uri")

    if ":" in label:
        issuer_from_label, account = label.split(":", 1)
        issuer_from_label = issuer_from_label.strip()
        account = account.strip()
    else:
        issuer_from_label = ""
        account = label.strip()

    query = parse_qs(parsed.query)

    def first(key: str) -> Optional[str]:
        values = query.get(key)
        if not values:
            return None
        return values[0]

    secret = first("secret")
    if not secret:
        raise TOTPValidationError("otpauth URI に secret が含まれていません", field="secret")

    issuer_query = first("issuer")
    issuer = issuer_query or issuer_from_label
    if not issuer:
        raise TOTPValidationError("otpauth URI に issuer が含まれていません", field="issuer")

    description = first("description") or first("comment")
    algorithm = (first("algorithm") or "SHA1").upper()
    digits_str = first("digits")
    period_str = first("period")

    try:
        digits = int(digits_str) if digits_str else 6
    except (TypeError, ValueError) as exc:
        raise TOTPValidationError("桁数の指定が正しくありません", field="digits") from exc
    try:
        period = int(period_str) if period_str else 30
    except (TypeError, ValueError) as exc:
        raise TOTPValidationError("有効期間の指定が正しくありません", field="period") from exc

    return OtpauthData(
        account=account,
        issuer=issuer,
        secret=secret,
        description=description,
        algorithm=algorithm,
        digits=digits,
        period=period,
    )
