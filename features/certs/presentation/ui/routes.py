"""証明書管理UIのルーティング"""
from __future__ import annotations

import json

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required
from cryptography.hazmat.primitives import serialization

from features.certs.application.dto import (
    GenerateCertificateMaterialInput,
    SignCertificateInput,
)
from features.certs.application.use_cases import (
    GenerateCertificateMaterialUseCase,
    GetIssuedCertificateUseCase,
    ListIssuedCertificatesUseCase,
    ListJwksUseCase,
    RevokeCertificateUseCase,
    SignCertificateUseCase,
)
from features.certs.domain.exceptions import (
    CertificateError,
    CertificateNotFoundError,
    CertificateValidationError,
    KeyGenerationError,
)
from features.certs.domain.usage import UsageType

from . import certs_ui_bp


_KEY_USAGE_CHOICES: list[tuple[str, str]] = [
    ("digitalSignature", _("digitalSignature - 電子署名")),
    ("contentCommitment", _("contentCommitment - コンテンツコミット")),
    ("keyEncipherment", _("keyEncipherment - 鍵暗号化")),
    ("dataEncipherment", _("dataEncipherment - データ暗号化")),
    ("keyAgreement", _("keyAgreement - 鍵共有")),
    ("keyCertSign", _("keyCertSign - 証明書署名")),
    ("crlSign", _("crlSign - CRL署名")),
    ("encipherOnly", _("encipherOnly - 暗号化専用")),
    ("decipherOnly", _("decipherOnly - 復号専用")),
]


def _ensure_permission() -> None:
    if not current_user.can("certificate:manage"):
        abort(403)


def _build_subject_from_form(form_data: dict[str, str]) -> dict[str, str]:
    mapping = {
        "C": "subject_c",
        "ST": "subject_st",
        "L": "subject_l",
        "O": "subject_o",
        "OU": "subject_ou",
        "CN": "subject_cn",
        "emailAddress": "subject_email",
    }
    subject = {}
    for oid, field_name in mapping.items():
        value = (form_data.get(field_name) or "").strip()
        if value:
            subject[oid] = value
    return subject


def _format_pem_lines(pem: str | None) -> str | None:
    if pem is None:
        return None
    return pem.strip()


def _usage_options() -> list[tuple[str, str]]:
    return [(usage.value, usage.name.replace("_", " ")) for usage in UsageType]


@certs_ui_bp.route("/")
@login_required
def index():
    _ensure_permission()

    usage_param = request.args.get("usage")
    usage_type: UsageType | None = None
    if usage_param:
        try:
            usage_type = UsageType.from_str(usage_param)
        except ValueError:
            flash(_("不正な用途種別が指定されました。"), "error")
            return redirect(url_for("certs_ui.index"))

    certificates = ListIssuedCertificatesUseCase().execute(usage_type)

    return render_template(
        "certs/index.html",
        certificates=certificates,
        selected_usage=usage_type.value if usage_type else "",
        usage_options=_usage_options(),
    )


@certs_ui_bp.route("/generate", methods=["GET", "POST"])
@login_required
def generate():
    _ensure_permission()

    context: dict[str, object] = {
        "usage_options": _usage_options(),
        "key_usage_choices": _KEY_USAGE_CHOICES,
    }

    if request.method == "POST":
        form = request.form
        subject = _build_subject_from_form(form)
        if not subject:
            flash(_("少なくとも1つのサブジェクト属性を入力してください。"), "error")
            return render_template("certs/generate.html", **context, form_data=form)

        key_type = form.get("key_type", "RSA")
        key_bits_raw = form.get("key_bits", "2048")
        try:
            key_bits = int(key_bits_raw)
        except (TypeError, ValueError):
            flash(_("鍵長は整数で指定してください。"), "error")
            return render_template("certs/generate.html", **context, form_data=form)

        days_raw = form.get("days", "365")
        try:
            days = int(days_raw)
        except (TypeError, ValueError):
            flash(_("有効日数は整数で指定してください。"), "error")
            return render_template("certs/generate.html", **context, form_data=form)

        try:
            usage_type = UsageType.from_str(form.get("usage_type"))
        except ValueError:
            flash(_("用途の指定が不正です。"), "error")
            return render_template("certs/generate.html", **context, form_data=form)

        key_usage = form.getlist("key_usage")
        is_ca = form.get("is_ca") == "on"

        material_input = GenerateCertificateMaterialInput(
            subject=subject,
            key_type=key_type,
            key_bits=key_bits,
            make_csr=True,
            usage_type=usage_type,
            key_usage=key_usage,
        )

        try:
            material_result = GenerateCertificateMaterialUseCase().execute(material_input)
            if not material_result.material.csr_pem:
                raise CertificateError("CSRの生成に失敗しました。")
            sign_input = SignCertificateInput(
                csr_pem=material_result.material.csr_pem,
                usage_type=usage_type,
                days=days,
                is_ca=is_ca,
                key_usage=key_usage,
            )
            sign_result = SignCertificateUseCase().execute(sign_input)
        except KeyGenerationError as exc:
            flash(str(exc), "error")
            return render_template("certs/generate.html", **context, form_data=form)
        except CertificateValidationError as exc:
            flash(str(exc), "error")
            return render_template("certs/generate.html", **context, form_data=form)
        except CertificateError as exc:
            flash(str(exc), "error")
            return render_template("certs/generate.html", **context, form_data=form)

        flash(_("証明書を生成しました。"), "success")
        context.update(
            {
                "form_data": form,
                "generated_material": material_result.material,
                "certificate_pem": sign_result.certificate_pem,
                "kid": sign_result.kid,
                "jwk_json": json.dumps(sign_result.jwk, indent=2, ensure_ascii=False),
            }
        )
        return render_template("certs/generate.html", **context)

    return render_template("certs/generate.html", **context)


@certs_ui_bp.route("/public")
@login_required
def public_keys():
    _ensure_permission()

    usage_infos = []
    jwks_use_case = ListJwksUseCase()
    for usage in UsageType:
        api_url = url_for("certs_api.jwks", usage=f"{usage.value}")
        jwks_result = jwks_use_case.execute(usage)
        usage_infos.append(
            {
                "usage": usage,
                "api_url": api_url,
                "key_count": len(jwks_result.get("keys", [])),
                "jwks_json": json.dumps(jwks_result, indent=2, ensure_ascii=False),
            }
        )

    return render_template("certs/public.html", usage_infos=usage_infos)


@certs_ui_bp.route("/<string:kid>")
@login_required
def detail(kid: str):
    _ensure_permission()

    try:
        certificate = GetIssuedCertificateUseCase().execute(kid)
    except CertificateNotFoundError:
        abort(404)

    x509_cert = certificate.certificate
    detail_context = {
        "certificate": certificate,
        "certificate_pem": _format_pem_lines(
            x509_cert.public_bytes(encoding=serialization.Encoding.PEM).decode("utf-8")
        ),
        "not_before": x509_cert.not_valid_before,
        "not_after": x509_cert.not_valid_after,
        "subject": x509_cert.subject.rfc4514_string(),
        "issuer": x509_cert.issuer.rfc4514_string(),
        "jwk_json": json.dumps(certificate.jwk, indent=2, ensure_ascii=False),
    }
    return render_template("certs/detail.html", **detail_context)


@certs_ui_bp.route("/revoke/<string:kid>", methods=["GET", "POST"])
@login_required
def revoke(kid: str):
    _ensure_permission()

    use_case = GetIssuedCertificateUseCase()
    try:
        certificate = use_case.execute(kid)
    except CertificateNotFoundError:
        abort(404)

    if request.method == "POST":
        reason = request.form.get("reason", "").strip() or None
        try:
            revoked = RevokeCertificateUseCase().execute(kid, reason)
        except CertificateNotFoundError:
            abort(404)
        flash(_("証明書を失効しました。"), "success")
        return redirect(url_for("certs_ui.detail", kid=revoked.kid))

    return render_template("certs/revoke.html", certificate=certificate)
