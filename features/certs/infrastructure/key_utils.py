"""鍵や証明書周りの共通関数"""
from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta
from typing import Iterable

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import NameOID

from features.certs.domain.exceptions import CertificateValidationError, KeyGenerationError
from features.certs.domain.usage import UsageType

from .encoding import to_base64url


_OID_MAP: dict[str, NameOID] = {
    "C": NameOID.COUNTRY_NAME,
    "ST": NameOID.STATE_OR_PROVINCE_NAME,
    "L": NameOID.LOCALITY_NAME,
    "O": NameOID.ORGANIZATION_NAME,
    "OU": NameOID.ORGANIZATIONAL_UNIT_NAME,
    "CN": NameOID.COMMON_NAME,
    "emailAddress": NameOID.EMAIL_ADDRESS,
}


class SubjectBuilder:
    """subject用のビルダー"""

    def __init__(self, subject_dict: dict[str, str] | None) -> None:
        self._subject_dict = subject_dict or {"CN": "Generated Certificate"}

    def build(self) -> x509.Name:
        attributes: list[x509.NameAttribute] = []
        for key, value in self._subject_dict.items():
            if not value:
                continue
            oid = _OID_MAP.get(key)
            if oid is None:
                raise CertificateValidationError(f"サポートされていないsubject属性です: {key}")
            normalized_value = self._normalize_value(oid, value)
            try:
                attributes.append(x509.NameAttribute(oid, normalized_value))
            except ValueError as exc:  # cryptographyの制約をドメイン例外として返す
                raise CertificateValidationError(
                    f"subject属性 {key} の値が不正です: {exc}"
                ) from exc

        if not attributes:
            raise CertificateValidationError("subjectが空です")
        return x509.Name(attributes)

    @staticmethod
    def _normalize_value(oid: NameOID, raw_value: str) -> str:
        value = raw_value.strip()
        if oid is NameOID.COUNTRY_NAME:
            if len(value) != 2:
                raise CertificateValidationError(
                    "国コード(C)はISO 3166-1の2文字コードで指定してください (例: JP)"
                )
            return value.upper()
        return value


def generate_private_key(key_type: str, key_bits: int) -> rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey:
    """鍵ペア生成"""

    key_type_upper = (key_type or "RSA").upper()
    if key_type_upper == "RSA":
        if key_bits < 2048:
            raise KeyGenerationError("RSA鍵長は2048以上である必要があります")
        return rsa.generate_private_key(public_exponent=65537, key_size=key_bits)
    if key_type_upper == "EC":
        return ec.generate_private_key(ec.SECP256R1())
    raise KeyGenerationError(f"未対応の鍵タイプです: {key_type}")


def serialize_private_key(key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey) -> str:
    return (
        key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
        .decode("utf-8")
    )


def serialize_public_key(key: rsa.RSAPublicKey | ec.EllipticCurvePublicKey) -> str:
    return (
        key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        .decode("utf-8")
    )


def build_csr(
    private_key: rsa.RSAPrivateKey | ec.EllipticCurvePrivateKey,
    subject: x509.Name,
    usage_type: UsageType,
    key_usage: Iterable[str] | None = None,
) -> x509.CertificateSigningRequest:
    builder = x509.CertificateSigningRequestBuilder().subject_name(subject)
    eku = _extended_key_usage_for_usage(usage_type)
    if eku is not None:
        builder = builder.add_extension(x509.ExtendedKeyUsage(eku), critical=False)

    key_usage_extension = build_key_usage_extension(key_usage)
    if key_usage_extension is not None:
        builder = builder.add_extension(key_usage_extension, critical=True)

    return builder.sign(private_key, hashes.SHA256())


def compute_thumbprint(public_key: rsa.RSAPublicKey | ec.EllipticCurvePublicKey) -> str:
    der = public_key.public_bytes(
        encoding=serialization.Encoding.DER,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return hashlib.sha1(der).hexdigest()


def csr_from_pem(csr_pem: str) -> x509.CertificateSigningRequest:
    try:
        return x509.load_pem_x509_csr(csr_pem.encode("utf-8"))
    except ValueError as exc:  # noqa: B904
        raise CertificateValidationError("CSRの読み込みに失敗しました") from exc


def certificate_to_jwk(cert: x509.Certificate, kid: str, usage: UsageType) -> dict:
    public_key = cert.public_key()
    if isinstance(public_key, rsa.RSAPublicKey):
        numbers = public_key.public_numbers()
        modulus = numbers.n.to_bytes((numbers.n.bit_length() + 7) // 8, "big")
        exponent = numbers.e.to_bytes((numbers.e.bit_length() + 7) // 8, "big")
        return {
            "kty": "RSA",
            "use": "sig" if usage != UsageType.ENCRYPTION else "enc",
            "alg": "RS256",
            "kid": kid,
            "n": to_base64url(modulus),
            "e": to_base64url(exponent),
            "x5t#S256": to_base64url(cert.fingerprint(hashes.SHA256())),
            "x5c": [
                base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode("ascii")
            ],
        }
    if isinstance(public_key, ec.EllipticCurvePublicKey):
        numbers = public_key.public_numbers()
        curve_name = _curve_to_jwk_name(public_key.curve)
        algorithm = {
            "P-256": "ES256",
            "P-384": "ES384",
            "P-521": "ES512",
        }[curve_name]
        return {
            "kty": "EC",
            "use": "sig" if usage != UsageType.ENCRYPTION else "enc",
            "alg": algorithm,
            "kid": kid,
            "crv": curve_name,
            "x": to_base64url(numbers.x.to_bytes((numbers.x.bit_length() + 7) // 8, "big")),
            "y": to_base64url(numbers.y.to_bytes((numbers.y.bit_length() + 7) // 8, "big")),
            "x5t#S256": to_base64url(cert.fingerprint(hashes.SHA256())),
            "x5c": [
                base64.b64encode(cert.public_bytes(serialization.Encoding.DER)).decode("ascii")
            ],
        }
    raise CertificateValidationError("現在RSA鍵のみサポートしています")


def _extended_key_usage_for_usage(usage: UsageType) -> list[x509.ObjectIdentifier] | None:
    if usage == UsageType.SERVER_SIGNING:
        return [x509.oid.ExtendedKeyUsageOID.SERVER_AUTH]
    if usage == UsageType.CLIENT_SIGNING:
        return [x509.oid.ExtendedKeyUsageOID.CLIENT_AUTH]
    if usage == UsageType.ENCRYPTION:
        return [x509.oid.ExtendedKeyUsageOID.EMAIL_PROTECTION]
    return None


def _create_key_usage_extension(usages: Iterable[str] | None) -> x509.KeyUsage | None:
    if usages is None:
        return None

    usage_set = {item for item in usages if item}
    if not usage_set:
        return None

    mapping = {
        "digitalSignature": "digital_signature",
        "contentCommitment": "content_commitment",
        "keyEncipherment": "key_encipherment",
        "dataEncipherment": "data_encipherment",
        "keyAgreement": "key_agreement",
        "keyCertSign": "key_cert_sign",
        "crlSign": "crl_sign",
        "encipherOnly": "encipher_only",
        "decipherOnly": "decipher_only",
    }

    params = {
        "digital_signature": False,
        "content_commitment": False,
        "key_encipherment": False,
        "data_encipherment": False,
        "key_agreement": False,
        "key_cert_sign": False,
        "crl_sign": False,
        "encipher_only": False,
        "decipher_only": False,
    }

    for usage in usage_set:
        attr = mapping.get(usage)
        if attr is None:
            raise CertificateValidationError(f"未対応のkeyUsageが指定されました: {usage}")
        params[attr] = True

    if params["encipher_only"] or params["decipher_only"]:
        params["key_agreement"] = True

    return x509.KeyUsage(**params)


def validity_range(days: int) -> tuple[datetime, datetime]:
    if days <= 0:
        raise CertificateValidationError("有効期限は1日以上で指定してください")
    now = datetime.utcnow()
    return now - timedelta(minutes=1), now + timedelta(days=days)


def build_key_usage_extension(usages: Iterable[str] | None) -> x509.KeyUsage | None:
    """公開用API: keyUsageエクステンションを生成"""

    return _create_key_usage_extension(usages)


def _curve_to_jwk_name(curve: ec.EllipticCurve) -> str:
    if isinstance(curve, ec.SECP256R1):
        return "P-256"
    if isinstance(curve, ec.SECP384R1):
        return "P-384"
    if isinstance(curve, ec.SECP521R1):
        return "P-521"
    raise CertificateValidationError("サポートされていないEC曲線です")
