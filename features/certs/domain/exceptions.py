"""証明書機能で利用する例外定義"""
from __future__ import annotations


class CertificateError(Exception):
    """証明書関連の基本例外"""


class CertificateValidationError(CertificateError):
    """入力やCSRの検証に失敗した際の例外"""


class CertificateSigningError(CertificateError):
    """証明書署名時の例外"""


class KeyGenerationError(CertificateError):
    """鍵生成時の例外"""


class CertificateNotFoundError(CertificateError):
    """証明書が存在しない場合の例外"""
