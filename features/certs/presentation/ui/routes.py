"""証明書管理UIのルーティング"""
from __future__ import annotations

import json

from http import HTTPStatus

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required

from features.certs.domain.usage import UsageType
from features.certs.presentation.ui.api_client import CertsApiClientError
from features.certs.presentation.ui.services import CertificateUiService

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


def _service() -> CertificateUiService:
    return CertificateUiService(current_app)


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

    service = _service()
    try:
        certificates = service.list_certificates(usage_type)
    except CertsApiClientError as exc:
        current_app.logger.exception("Failed to load certificates via API")
        flash(_("証明書一覧の取得に失敗しました: %(message)s", message=str(exc)), "error")
        certificates = []

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

        service = _service()

        try:
            material_result = service.generate_material(
                subject=subject,
                key_type=key_type,
                key_bits=key_bits,
                make_csr=True,
                usage_type=usage_type,
                key_usage=key_usage,
            )
            if not material_result.csr_pem:
                raise CertsApiClientError(
                    _("CSRの生成に失敗しました。"), HTTPStatus.INTERNAL_SERVER_ERROR
                )
            sign_result = service.sign_certificate(
                csr_pem=material_result.csr_pem,
                usage_type=usage_type,
                days=days,
                is_ca=is_ca,
                key_usage=key_usage,
            )
        except CertsApiClientError as exc:
            current_app.logger.exception("Failed to generate certificate via API")
            flash(str(exc), "error")
            return render_template("certs/generate.html", **context, form_data=form)

        flash(_("証明書を生成しました。"), "success")
        context.update(
            {
                "form_data": form,
                "generated_material": material_result,
                "certificate_pem": _format_pem_lines(sign_result.certificate_pem),
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

    service = _service()

    try:
        certificates = service.list_certificates()
    except CertsApiClientError as exc:
        current_app.logger.exception("Failed to load certificates via API for JWKS list")
        flash(_("証明書一覧の取得に失敗しました: %(message)s", message=str(exc)), "error")
        certificates = []

    group_infos: list[dict[str, object]] = []
    seen_groups: dict[str, UsageType] = {}
    for certificate in certificates:
        if not certificate.group_code:
            continue
        if certificate.group_code not in seen_groups:
            seen_groups[certificate.group_code] = certificate.usage_type

    for group_code, usage in sorted(seen_groups.items(), key=lambda item: (item[1].value, item[0])):
        api_url = url_for("certs_api.jwks", group_code=group_code)
        try:
            jwks_result = service.list_jwks(group_code)
        except CertsApiClientError as exc:
            current_app.logger.exception(
                "Failed to fetch JWKS via API",
                extra={"group_code": group_code},
            )
            flash(_("公開鍵一覧の取得に失敗しました: %(message)s", message=str(exc)), "error")
            jwks_result = {"keys": []}
        group_infos.append(
            {
                "group_code": group_code,
                "usage": usage,
                "api_url": api_url,
                "key_count": len(jwks_result.get("keys", [])),
                "jwks_json": json.dumps(jwks_result, indent=2, ensure_ascii=False),
            }
        )

    return render_template("certs/public.html", group_infos=group_infos)


@certs_ui_bp.route("/<string:kid>")
@login_required
def detail(kid: str):
    _ensure_permission()

    try:
        certificate = _service().get_certificate(kid)
    except CertsApiClientError as exc:
        if exc.status_code == HTTPStatus.NOT_FOUND:
            abort(404)
        current_app.logger.exception("Failed to load certificate detail via API")
        flash(str(exc), "error")
        return redirect(url_for("certs_ui.index"))

    detail_context = {
        "certificate": certificate,
        "certificate_pem": _format_pem_lines(certificate.certificate_pem),
        "not_before": certificate.not_before,
        "not_after": certificate.not_after,
        "subject": certificate.subject,
        "issuer": certificate.issuer,
        "jwk_json": json.dumps(certificate.jwk, indent=2, ensure_ascii=False),
    }
    return render_template("certs/detail.html", **detail_context)


@certs_ui_bp.route("/revoke/<string:kid>", methods=["GET", "POST"])
@login_required
def revoke(kid: str):
    _ensure_permission()

    try:
        certificate = _service().get_certificate(kid)
    except CertsApiClientError as exc:
        if exc.status_code == HTTPStatus.NOT_FOUND:
            abort(404)
        current_app.logger.exception("Failed to load certificate for revoke via API")
        flash(str(exc), "error")
        return redirect(url_for("certs_ui.index"))

    if request.method == "POST":
        reason = request.form.get("reason", "").strip() or None
        try:
            revoked = _service().revoke_certificate(kid, reason)
        except CertsApiClientError as exc:
            if exc.status_code == HTTPStatus.NOT_FOUND:
                abort(404)
            current_app.logger.exception("Failed to revoke certificate via API")
            flash(str(exc), "error")
            return redirect(url_for("certs_ui.revoke", kid=kid))
        flash(_("証明書を失効しました。"), "success")
        return redirect(url_for("certs_ui.detail", kid=revoked.kid))

    return render_template("certs/revoke.html", certificate=certificate)
