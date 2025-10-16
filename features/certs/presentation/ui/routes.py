"""証明書管理UIのルート"""
from __future__ import annotations

import json
from datetime import datetime
from http import HTTPStatus

from flask import (
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    url_for,
    session,
)
from flask_babel import gettext as _, lazy_gettext as _l
from flask_login import current_user, login_required
import re

from features.certs.domain.usage import UsageType
from features.certs.presentation.ui.api_client import CertsApiClientError
from features.certs.presentation.ui.services import CertificateUiService

from . import certs_ui_bp

_KEY_USAGE_CHOICES: list[tuple[str, str]] = [
    ("digitalSignature", _("digitalSignature - digital signature")),
    ("contentCommitment", _("contentCommitment - content commitment")),
    ("keyEncipherment", _("keyEncipherment - key encipherment")),
    ("dataEncipherment", _("dataEncipherment - data encipherment")),
    ("keyAgreement", _("keyAgreement - key agreement")),
    ("keyCertSign", _("keyCertSign - certificate signing")),
    ("crlSign", _("crlSign - CRL signing")),
    ("encipherOnly", _("encipherOnly - encipher only")),
    ("decipherOnly", _("decipherOnly - decipher only")),
]

_SUBJECT_FIELD_DEFINITIONS: list[tuple[str, str, str]] = [
    ("C", "subject_c", _("Country (C)")),
    ("ST", "subject_st", _("State or Province (ST)")),
    ("L", "subject_l", _("Locality (L)")),
    ("O", "subject_o", _("Organization (O)")),
    ("OU", "subject_ou", _("Organizational Unit (OU)")),
    ("CN", "subject_cn", _("Common Name (CN)")),
    ("emailAddress", "subject_email", _("Email Address")),
]

_KEY_TYPE_OPTIONS = ["RSA", "EC"]

_SUBJECT_VALUE_PATTERN = r"[A-Za-z0-9\s,.\-@_/+=:()']+"
_SUBJECT_VALUE_REGEX = re.compile(rf"^{_SUBJECT_VALUE_PATTERN}$")
_SUBJECT_ALLOWED_CHARS = _l("Allowed characters: letters, numbers, spaces, and - , . @ _ / + = : ( ) '.")


def _subject_invalid_message() -> str:
    return _("Enter a valid subject value. %(allowed)s", allowed=_SUBJECT_ALLOWED_CHARS)


def _ensure_permission() -> None:
    if not current_user.can("certificate:manage"):
        abort(403)


def _build_subject_from_form(form_data: dict[str, str]) -> dict[str, str]:
    subject: dict[str, str] = {}
    for oid, field_name, _label in _SUBJECT_FIELD_DEFINITIONS:
        value = (form_data.get(field_name) or "").strip()
        if not value:
            continue
        if not _SUBJECT_VALUE_REGEX.match(value):
            raise ValueError(_subject_invalid_message())
        subject[oid] = value
    return subject


def _subject_to_form_values(subject: dict[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for oid, field_name, _label in _SUBJECT_FIELD_DEFINITIONS:
        values[field_name] = subject.get(oid, "")
    return values


def _usage_options() -> list[tuple[str, str]]:
    return [(usage.value, usage.name.replace("_", " ")) for usage in UsageType]


def _service() -> CertificateUiService:
    return CertificateUiService(current_app)


def _parse_usage(value: str | None) -> UsageType:
    if not value:
        raise ValueError("usage type is required")
    return UsageType.from_str(value)


def _parse_int(value: str | None, *, default: int | None = None) -> int | None:
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid integer") from exc


@certs_ui_bp.route("/")
@login_required
def index():
    _ensure_permission()

    service = _service()
    try:
        groups = service.list_groups()
    except CertsApiClientError as exc:
        current_app.logger.exception("Failed to load certificate groups via API")
        flash(_("Failed to load certificate groups: %(message)s", message=str(exc)), "error")
        groups = []

    return render_template(
        "certs/groups.html",
        groups=groups,
        usage_options=_usage_options(),
        subject_fields=_SUBJECT_FIELD_DEFINITIONS,
        subject_value_pattern=_SUBJECT_VALUE_PATTERN,
        subject_value_hint=_SUBJECT_ALLOWED_CHARS,
        key_type_options=_KEY_TYPE_OPTIONS,
    )


@certs_ui_bp.route("/groups/create", methods=["POST"])
@login_required
def create_group():
    _ensure_permission()

    form = request.form
    group_code = (form.get("group_code") or "").strip()
    if not group_code:
        flash(_("Group code is required."), "error")
        return redirect(url_for("certs_ui.index"))

    display_name = (form.get("display_name") or "").strip() or None
    try:
        usage_type = _parse_usage(form.get("usage_type"))
    except ValueError:
        flash(_("Invalid usage type specified."), "error")
        return redirect(url_for("certs_ui.index"))

    key_type = (form.get("key_type") or "RSA").strip().upper()
    key_curve = (form.get("key_curve") or "").strip() or None

    try:
        key_size = _parse_int(form.get("key_size"))
    except ValueError:
        flash(_("Key size must be a number."), "error")
        return redirect(url_for("certs_ui.index"))

    auto_rotate = form.get("auto_rotate") == "on"
    try:
        rotation_threshold_days = _parse_int(form.get("rotation_threshold_days"), default=30)
    except ValueError:
        flash(_("Rotation threshold must be a number."), "error")
        return redirect(url_for("certs_ui.index"))
    if rotation_threshold_days is None or rotation_threshold_days <= 0:
        flash(_("Rotation threshold must be greater than zero."), "error")
        return redirect(url_for("certs_ui.index"))

    try:
        subject = _build_subject_from_form(form)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("certs_ui.index"))
    if not subject:
        flash(_("Enter at least one subject attribute."), "error")
        return redirect(url_for("certs_ui.index"))

    service = _service()
    try:
        service.create_group(
            group_code=group_code,
            display_name=display_name,
            usage_type=usage_type,
            key_type=key_type,
            key_curve=key_curve,
            key_size=key_size,
            auto_rotate=auto_rotate,
            rotation_threshold_days=rotation_threshold_days,
            subject=subject,
        )
    except CertsApiClientError as exc:
        current_app.logger.exception("Failed to create certificate group")
        flash(_("Failed to create certificate group: %(message)s", message=str(exc)), "error")
    else:
        flash(_("Certificate group created."), "success")

    return redirect(url_for("certs_ui.index"))


@certs_ui_bp.route("/groups/<string:group_code>/update", methods=["POST"])
@login_required
def update_group(group_code: str):
    _ensure_permission()

    form = request.form
    display_name = (form.get("display_name") or "").strip() or None
    try:
        usage_type = _parse_usage(form.get("usage_type"))
    except ValueError:
        flash(_("Invalid usage type specified."), "error")
        return redirect(url_for("certs_ui.index"))

    key_type = (form.get("key_type") or "RSA").strip().upper()
    key_curve = (form.get("key_curve") or "").strip() or None

    try:
        key_size = _parse_int(form.get("key_size"))
    except ValueError:
        flash(_("Key size must be a number."), "error")
        return redirect(url_for("certs_ui.index"))

    auto_rotate = form.get("auto_rotate") == "on"
    try:
        rotation_threshold_days = _parse_int(form.get("rotation_threshold_days"), default=30)
    except ValueError:
        flash(_("Rotation threshold must be a number."), "error")
        return redirect(url_for("certs_ui.index"))
    if rotation_threshold_days is None or rotation_threshold_days <= 0:
        flash(_("Rotation threshold must be greater than zero."), "error")
        return redirect(url_for("certs_ui.index"))

    try:
        subject = _build_subject_from_form(form)
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("certs_ui.index"))
    if not subject:
        flash(_("Enter at least one subject attribute."), "error")
        return redirect(url_for("certs_ui.index"))

    service = _service()
    try:
        service.update_group(
            group_code,
            display_name=display_name,
            usage_type=usage_type,
            key_type=key_type,
            key_curve=key_curve,
            key_size=key_size,
            auto_rotate=auto_rotate,
            rotation_threshold_days=rotation_threshold_days,
            subject=subject,
        )
    except CertsApiClientError as exc:
        current_app.logger.exception("Failed to update certificate group")
        flash(_("Failed to update certificate group: %(message)s", message=str(exc)), "error")
    else:
        flash(_("Certificate group updated."), "success")

    return redirect(url_for("certs_ui.index"))


@certs_ui_bp.route("/groups/<string:group_code>/delete", methods=["POST"])
@login_required
def delete_group(group_code: str):
    _ensure_permission()

    service = _service()
    try:
        service.delete_group(group_code)
    except CertsApiClientError as exc:
        current_app.logger.exception("Failed to delete certificate group")
        message = str(exc)
        if exc.status_code == HTTPStatus.CONFLICT:
            flash(
                _("Cannot delete the group because certificates exist: %(message)s", message=message),
                "error",
            )
        else:
            flash(_("Failed to delete certificate group: %(message)s", message=message), "error")
    else:
        flash(_("Certificate group deleted."), "success")

    return redirect(url_for("certs_ui.index"))


@certs_ui_bp.route("/groups/<string:group_code>")
@login_required
def group_detail(group_code: str):
    _ensure_permission()

    service = _service()
    try:
        group, certificates = service.list_group_certificates(group_code)
    except CertsApiClientError as exc:
        if exc.status_code == HTTPStatus.NOT_FOUND:
            abort(404)
        current_app.logger.exception("Failed to load certificates for group", extra={"group_code": group_code})
        flash(_("Failed to load certificates: %(message)s", message=str(exc)), "error")
        return redirect(url_for("certs_ui.index"))

    issued_certificate = session.pop("certs_last_issued", None)

    jwks_url = url_for("certs_api.jwks", group_code=group_code, _external=True)
    subject_form_values = _subject_to_form_values(group.subject_dict())

    return render_template(
        "certs/group_detail.html",
        group=group,
        certificates=certificates,
        jwks_url=jwks_url,
        key_usage_choices=_KEY_USAGE_CHOICES,
        issued_certificate=issued_certificate,
        subject_fields=_SUBJECT_FIELD_DEFINITIONS,
        subject_value_pattern=_SUBJECT_VALUE_PATTERN,
        subject_value_hint=_SUBJECT_ALLOWED_CHARS,
        subject_form_values=subject_form_values,
    )


@certs_ui_bp.route("/groups/<string:group_code>/issue", methods=["POST"])
@login_required
def issue_certificate(group_code: str):
    _ensure_permission()

    form = request.form
    subject_overrides = _build_subject_from_form(form)

    try:
        valid_days = _parse_int(form.get("valid_days"))
    except ValueError:
        flash(_("Validity days must be a number."), "error")
        return redirect(url_for("certs_ui.group_detail", group_code=group_code))

    key_usage = form.getlist("key_usage")

    service = _service()
    try:
        result = service.issue_certificate_for_group(
            group_code,
            subject_overrides=subject_overrides or None,
            valid_days=valid_days,
            key_usage=key_usage or None,
        )
    except CertsApiClientError as exc:
        current_app.logger.exception("Failed to issue certificate for group", extra={"group_code": group_code})
        flash(_("Failed to issue certificate: %(message)s", message=str(exc)), "error")
        return redirect(url_for("certs_ui.group_detail", group_code=group_code))

    flash(_("Certificate issued successfully."), "success")
    session["certs_last_issued"] = {
        "kid": result.kid,
        "certificatePem": result.certificate_pem,
        "privateKeyPem": result.private_key_pem,
        "usageType": result.usage_type.value,
    }
    return redirect(url_for("certs_ui.group_detail", group_code=group_code))


@certs_ui_bp.route(
    "/groups/<string:group_code>/certificates/<string:kid>/revoke",
    methods=["POST"],
)
@login_required
def revoke_certificate_in_group(group_code: str, kid: str):
    _ensure_permission()

    reason = (request.form.get("reason") or "").strip() or None

    service = _service()
    try:
        service.revoke_certificate_in_group(group_code, kid, reason=reason)
    except CertsApiClientError as exc:
        if exc.status_code == HTTPStatus.NOT_FOUND:
            abort(404)
        current_app.logger.exception(
            "Failed to revoke certificate in group",
            extra={"group_code": group_code, "kid": kid},
        )
        flash(_("Failed to revoke certificate: %(message)s", message=str(exc)), "error")
    else:
        flash(_("Certificate revoked."), "success")

    return redirect(url_for("certs_ui.group_detail", group_code=group_code))


@certs_ui_bp.route("/search", methods=["GET"])
@login_required
def search():
    _ensure_permission()

    service = _service()
    try:
        groups = service.list_groups()
    except CertsApiClientError as exc:
        current_app.logger.exception("Failed to load groups for search")
        flash(_("Failed to load groups: %(message)s", message=str(exc)), "error")
        groups = []

    filters = {
        "kid": (request.args.get("kid") or "").strip(),
        "group": (request.args.get("group") or "").strip(),
        "usage": (request.args.get("usage") or "").strip(),
        "subject": (request.args.get("subject") or "").strip(),
        "issued_from": (request.args.get("issued_from") or "").strip(),
        "issued_to": (request.args.get("issued_to") or "").strip(),
        "expires_from": (request.args.get("expires_from") or "").strip(),
        "expires_to": (request.args.get("expires_to") or "").strip(),
        "revoked": (request.args.get("revoked") or "").strip(),
    }

    results = None
    if any(filters.values()):
        try:
            usage_type = UsageType.from_str(filters["usage"]) if filters["usage"] else None
        except ValueError:
            flash(_("Invalid usage type specified."), "error")
            usage_type = None

        revoked_param = filters["revoked"].lower()
        revoked: bool | None
        if revoked_param in {"", "any"}:
            revoked = None
        elif revoked_param in {"true", "revoked"}:
            revoked = True
        elif revoked_param in {"false", "active"}:
            revoked = False
        else:
            flash(_("Invalid revoked flag."), "error")
            revoked = None

        def _parse_dt(value: str) -> datetime | None:
            if not value:
                return None
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                flash(_("Use ISO 8601 format for date filters."), "error")
                return None

        issued_from_dt = _parse_dt(filters["issued_from"])
        issued_to_dt = _parse_dt(filters["issued_to"])
        expires_from_dt = _parse_dt(filters["expires_from"])
        expires_to_dt = _parse_dt(filters["expires_to"])

        try:
            results = service.search_certificates(
                kid=filters["kid"] or None,
                group_code=filters["group"] or None,
                usage_type=usage_type,
                subject=filters["subject"] or None,
                issued_from=issued_from_dt,
                issued_to=issued_to_dt,
                expires_from=expires_from_dt,
                expires_to=expires_to_dt,
                revoked=revoked,
            )
        except CertsApiClientError as exc:
            current_app.logger.exception("Failed to search certificates via API")
            flash(_("Failed to search certificates: %(message)s", message=str(exc)), "error")
            results = None

    return render_template(
        "certs/search.html",
        usage_options=_usage_options(),
        groups=groups,
        filters=filters,
        results=results,
        current_url=request.full_path,
    )


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
        "certificate_pem": certificate.certificate_pem.strip(),
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

    next_url = request.values.get("next")

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
        flash(_("Certificate revoked."), "success")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("certs_ui.detail", kid=revoked.kid))

    return render_template("certs/revoke.html", certificate=certificate, next_url=next_url)
