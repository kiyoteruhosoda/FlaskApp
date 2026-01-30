"""証明書管理UIのルート"""
from __future__ import annotations

import json
import re
from datetime import datetime
from http import HTTPStatus

from flask import (
    abort,
    current_app,
    flash as flask_flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_babel import gettext as _
from flask_login import current_user, login_required

from bounded_contexts.certs.domain.usage import UsageType
from bounded_contexts.certs.presentation.ui.api_client import CertsApiClientError
from bounded_contexts.certs.presentation.ui.services import CertificateUiService

from . import certs_ui_bp

_GROUP_CODE_PATTERN = re.compile(r"^[a-z0-9_-]+$")

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

_EXTENDED_KEY_USAGE_CHOICES: list[tuple[str, str]] = [
    ("serverAuth", _("serverAuth - TLS WWW server authentication")),
    ("clientAuth", _("clientAuth - TLS WWW client authentication")),
    ("codeSigning", _("codeSigning - Code signing")),
    ("emailProtection", _("emailProtection - E-mail protection")),
    ("timeStamping", _("timeStamping - Time stamping")),
    ("ocspSigning", _("ocspSigning - OCSP signing")),
    ("ipsecEndSystem", _("ipsecEndSystem - IPsec end system")),
    ("ipsecTunnel", _("ipsecTunnel - IPsec tunnel")),
    ("ipsecUser", _("ipsecUser - IPsec user")),
    ("anyExtendedKeyUsage", _("anyExtendedKeyUsage - Any extended key usage")),
]

_SUBJECT_FIELD_DEFINITIONS: list[tuple[str, str, str, bool]] = [
    ("C", "subject_c", _("Country (C)"), True),
    ("ST", "subject_st", _("State or Province (ST)"), False),
    ("L", "subject_l", _("Locality (L)"), False),
    ("O", "subject_o", _("Organization (O)"), False),
    ("OU", "subject_ou", _("Organizational Unit (OU)"), False),
    ("CN", "subject_cn", _("Common Name (CN)"), True),
    ("emailAddress", "subject_email", _("Email Address"), False),
]


class SubjectValidationError(ValueError):
    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors

def _ensure_permission() -> None:
    if not current_user.can("certificate:manage"):
        abort(403)


def _usage_key_presets() -> dict[str, list[dict[str, str | int | None]]]:
    return {
        UsageType.SERVER_SIGNING.value: [
            {
                "label": _("RSA 2048 (recommended)"),
                "keyType": "RSA",
                "keyCurve": None,
                "keySize": 2048,
            },
            {
                "label": _("RSA 4096"),
                "keyType": "RSA",
                "keyCurve": None,
                "keySize": 4096,
            },
            {
                "label": _("EC P-256"),
                "keyType": "EC",
                "keyCurve": "P-256",
                "keySize": None,
            },
            {
                "label": _("EC P-384"),
                "keyType": "EC",
                "keyCurve": "P-384",
                "keySize": None,
            },
        ],
        UsageType.CLIENT_SIGNING.value: [
            {
                "label": _("EC P-256 (recommended)"),
                "keyType": "EC",
                "keyCurve": "P-256",
                "keySize": None,
            },
            {
                "label": _("EC P-384"),
                "keyType": "EC",
                "keyCurve": "P-384",
                "keySize": None,
            },
            {
                "label": _("RSA 2048"),
                "keyType": "RSA",
                "keyCurve": None,
                "keySize": 2048,
            },
        ],
        UsageType.ENCRYPTION.value: [
            {
                "label": _("RSA 2048 (recommended)"),
                "keyType": "RSA",
                "keyCurve": None,
                "keySize": 2048,
            },
            {
                "label": _("RSA 3072"),
                "keyType": "RSA",
                "keyCurve": None,
                "keySize": 3072,
            },
            {
                "label": _("RSA 4096"),
                "keyType": "RSA",
                "keyCurve": None,
                "keySize": 4096,
            },
        ],
    }


def _build_subject_from_form(form_data: dict[str, str]) -> dict[str, str]:
    subject: dict[str, str] = {}
    for oid, field_name, _label, _required in _SUBJECT_FIELD_DEFINITIONS:
        value = (form_data.get(field_name) or "").strip()
        if value:
            subject[oid] = value
    return subject


def _validate_subject_template(form_data: dict[str, str], *, usage_type: UsageType) -> dict[str, str]:
    if usage_type in {UsageType.SERVER_SIGNING, UsageType.CLIENT_SIGNING}:
        return _build_subject_from_form(form_data)

    errors: list[str] = []
    subject: dict[str, str] = {}

    for oid, field_name, label, required in _SUBJECT_FIELD_DEFINITIONS:
        raw_value = (form_data.get(field_name) or "").strip()
        if not raw_value:
            if required:
                errors.append(_("%(label)s is required.", label=label))
            continue

        if not raw_value.isascii():
            errors.append(_("%(label)s must use ASCII characters.", label=label))
            continue

        value = raw_value
        if oid == "C":
            normalized = value.upper()
            if len(normalized) != 2 or not normalized.isalpha():
                errors.append(_("Country (C) must be a two-letter ISO 3166-1 alpha-2 code (e.g., JP)."))
                continue
            value = normalized

        subject[oid] = value

    if not subject and not errors:
        errors.append(_("At least one subject attribute is required."))

    if errors:
        raise SubjectValidationError(errors)

    return subject


def _subject_to_form_values(subject: dict[str, str]) -> dict[str, str]:
    values: dict[str, str] = {}
    for oid, field_name, _label, _required in _SUBJECT_FIELD_DEFINITIONS:
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
        flask_flash(_("Failed to load certificate groups: %(message)s", message=str(exc)), "error")
        groups = []

    stored_form_state = session.pop("certs_create_group_form", None)
    create_form_values: dict[str, str] = {}
    create_form_errors: list[str] = []
    show_create_modal = False
    if stored_form_state:
        create_form_values = stored_form_state.get("values", {})
        show_create_modal = bool(stored_form_state.get("show_modal"))
        raw_errors = stored_form_state.get("errors")
        if raw_errors:
            if isinstance(raw_errors, (list, tuple)):
                create_form_errors = [str(message) for message in raw_errors if message]
            else:
                create_form_errors = [str(raw_errors)]

    stored_edit_form = session.pop("certs_edit_group_form", None)
    edit_form_initial: dict[str, object] | None = None
    show_edit_modal = False
    edit_form_errors: list[str] = []
    if stored_edit_form:
        values = stored_edit_form.get("values", {}) if isinstance(stored_edit_form, dict) else {}
        group_code_value = (
            stored_edit_form.get("group_code") if isinstance(stored_edit_form, dict) else None
        ) or values.get("group_code")
        subject_values = {
            oid: values.get(field_name, "")
            for oid, field_name, _label, _required in _SUBJECT_FIELD_DEFINITIONS
        }
        edit_form_initial = {
            "groupCode": group_code_value or "",
            "displayName": values.get("display_name", ""),
            "usageType": values.get("usage_type", ""),
            "keyType": values.get("key_type", ""),
            "keyCurve": values.get("key_curve", ""),
            "keySize": values.get("key_size", ""),
            "autoRotate": values.get("auto_rotate") == "on",
            "rotationThresholdDays": values.get("rotation_threshold_days", ""),
            "subject": subject_values,
        }
        show_edit_modal = bool(stored_edit_form.get("show_modal"))
        raw_edit_errors = stored_edit_form.get("errors") if isinstance(stored_edit_form, dict) else None
        if raw_edit_errors:
            if isinstance(raw_edit_errors, (list, tuple)):
                edit_form_errors = [str(message) for message in raw_edit_errors if message]
            else:
                edit_form_errors = [str(raw_edit_errors)]

    if "auto_rotate" not in create_form_values:
        create_form_values["auto_rotate"] = "on"
    if "rotation_threshold_days" not in create_form_values:
        create_form_values["rotation_threshold_days"] = "30"
    if not create_form_values.get("usage_type"):
        create_form_values["usage_type"] = UsageType.SERVER_SIGNING.value

    required_subject_field_names = [
        field_name
        for _oid, field_name, _label, required in _SUBJECT_FIELD_DEFINITIONS
        if required
    ]

    return render_template(
        "certs/groups.html",
        groups=groups,
        usage_options=_usage_options(),
        subject_fields=_SUBJECT_FIELD_DEFINITIONS,
        required_subject_field_names=required_subject_field_names,
        key_presets=_usage_key_presets(),
        create_form_values=create_form_values,
        create_form_errors=create_form_errors,
        show_create_modal=show_create_modal,
        edit_form_initial=edit_form_initial,
        edit_form_errors=edit_form_errors,
        show_edit_modal=show_edit_modal,
    )


@certs_ui_bp.route("/groups/create", methods=["POST"])
@login_required
def create_group():
    _ensure_permission()

    form = request.form

    def _remember_form_state(*, errors: list[str] | None = None) -> None:
        values = form.to_dict(flat=True)
        values["auto_rotate"] = "on" if form.get("auto_rotate") == "on" else "off"
        state: dict[str, object] = {
            "values": values,
            "show_modal": True,
        }
        if errors:
            state["errors"] = [str(message) for message in errors if message]
        session["certs_create_group_form"] = state
    group_code = (form.get("group_code") or "").strip()
    if not group_code:
        message = _("Group code is required.")
        _remember_form_state(errors=[message])
        flask_flash(message, "error")
        return redirect(url_for("certs_ui.index"))

    if not _GROUP_CODE_PATTERN.fullmatch(group_code):
        message = _("Group code must contain only lowercase letters, numbers, hyphen, or underscore.")
        _remember_form_state(errors=[message])
        flask_flash(message, "error")
        return redirect(url_for("certs_ui.index"))

    display_name = (form.get("display_name") or "").strip() or None
    try:
        usage_type = _parse_usage(form.get("usage_type"))
    except ValueError:
        message = _("Invalid usage type specified.")
        _remember_form_state(errors=[message])
        flask_flash(message, "error")
        return redirect(url_for("certs_ui.index"))

    key_type = (form.get("key_type") or "RSA").strip().upper()
    key_curve = (form.get("key_curve") or "").strip() or None

    try:
        key_size = _parse_int(form.get("key_size"))
    except ValueError:
        message = _("Key size must be a number.")
        _remember_form_state(errors=[message])
        flask_flash(message, "error")
        return redirect(url_for("certs_ui.index"))

    auto_rotate = form.get("auto_rotate") == "on"
    try:
        rotation_threshold_days = _parse_int(form.get("rotation_threshold_days"), default=30)
    except ValueError:
        message = _("Rotation threshold must be a number.")
        _remember_form_state(errors=[message])
        flask_flash(message, "error")
        return redirect(url_for("certs_ui.index"))
    if rotation_threshold_days is None or rotation_threshold_days <= 0:
        message = _("Rotation threshold must be greater than zero.")
        _remember_form_state(errors=[message])
        flask_flash(message, "error")
        return redirect(url_for("certs_ui.index"))

    try:
        subject = _validate_subject_template(form, usage_type=usage_type)
    except SubjectValidationError as exc:
        _remember_form_state(errors=list(exc.errors))
        for message in exc.errors:
            flask_flash(message, "error")
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
        message = _("Failed to create certificate group: %(message)s", message=str(exc))
        _remember_form_state(errors=[message])
        flask_flash(message, "error")
    else:
        session.pop("certs_create_group_form", None)
        flask_flash(_("Certificate group created."), "success")

    return redirect(url_for("certs_ui.index"))


@certs_ui_bp.route("/groups/<string:group_code>/update", methods=["POST"])
@login_required
def update_group(group_code: str):
    _ensure_permission()

    form = request.form

    def _remember_edit_form_state(*, errors: list[str] | None = None) -> None:
        values = form.to_dict(flat=True)
        values["auto_rotate"] = "on" if form.get("auto_rotate") == "on" else "off"
        state: dict[str, object] = {
            "group_code": group_code,
            "values": values,
            "show_modal": True,
        }
        if errors:
            state["errors"] = [str(message) for message in errors if message]
        session["certs_edit_group_form"] = state

    display_name = (form.get("display_name") or "").strip() or None
    try:
        usage_type = _parse_usage(form.get("usage_type"))
    except ValueError:
        message = _("Invalid usage type specified.")
        _remember_edit_form_state(errors=[message])
        flask_flash(message, "error")
        return redirect(url_for("certs_ui.index"))

    key_type = (form.get("key_type") or "RSA").strip().upper()
    key_curve = (form.get("key_curve") or "").strip() or None

    try:
        key_size = _parse_int(form.get("key_size"))
    except ValueError:
        message = _("Key size must be a number.")
        _remember_edit_form_state(errors=[message])
        flask_flash(message, "error")
        return redirect(url_for("certs_ui.index"))

    auto_rotate = form.get("auto_rotate") == "on"
    try:
        rotation_threshold_days = _parse_int(form.get("rotation_threshold_days"), default=30)
    except ValueError:
        message = _("Rotation threshold must be a number.")
        _remember_edit_form_state(errors=[message])
        flask_flash(message, "error")
        return redirect(url_for("certs_ui.index"))
    if rotation_threshold_days is None or rotation_threshold_days <= 0:
        message = _("Rotation threshold must be greater than zero.")
        _remember_edit_form_state(errors=[message])
        flask_flash(message, "error")
        return redirect(url_for("certs_ui.index"))

    try:
        subject = _validate_subject_template(form, usage_type=usage_type)
    except SubjectValidationError as exc:
        _remember_edit_form_state(errors=list(exc.errors))
        for message in exc.errors:
            flask_flash(message, "error")
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
        message = _("Failed to update certificate group: %(message)s", message=str(exc))
        _remember_edit_form_state(errors=[message])
        flask_flash(message, "error")
    else:
        session.pop("certs_edit_group_form", None)
        flask_flash(_("Certificate group updated."), "success")

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
            flask_flash(
                _(
                    "Cannot delete the group because active certificates exist: %(message)s",
                    message=message,
                ),
                "error",
            )
        else:
            flask_flash(_("Failed to delete certificate group: %(message)s", message=message), "error")
    else:
        flask_flash(_("Certificate group deleted."), "success")

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
        flask_flash(_("Failed to load certificates: %(message)s", message=str(exc)), "error")
        return redirect(url_for("certs_ui.index"))

    issued_certificate = session.pop("certs_last_issued", None)

    jwks_url = url_for("certs_api.jwks", group_code=group_code, _external=True)
    subject_form_values = _subject_to_form_values(group.subject)

    required_subject_field_names = [
        field_name
        for _oid, field_name, _label, required in _SUBJECT_FIELD_DEFINITIONS
        if required
    ]

    return render_template(
        "certs/group_detail.html",
        group=group,
        certificates=certificates,
        jwks_url=jwks_url,
        key_usage_choices=_KEY_USAGE_CHOICES,
        issued_certificate=issued_certificate,
        subject_fields=_SUBJECT_FIELD_DEFINITIONS,
        required_subject_field_names=required_subject_field_names,
        subject_form_values=subject_form_values,
    )


@certs_ui_bp.route("/groups/<string:group_code>/rotation", methods=["POST"])
@login_required
def update_group_rotation(group_code: str):
    _ensure_permission()

    service = _service()
    try:
        group, _ = service.list_group_certificates(group_code)
    except CertsApiClientError as exc:
        if exc.status_code == HTTPStatus.NOT_FOUND:
            abort(404)
        current_app.logger.exception(
            "Failed to load group before updating rotation",
            extra={"group_code": group_code},
        )
        flask_flash(_("Failed to update rotation setting: %(message)s", message=str(exc)), "error")
        return redirect(url_for("certs_ui.group_detail", group_code=group_code))

    auto_rotate = request.form.get("auto_rotate") == "on"

    try:
        service.update_group(
            group_code,
            display_name=group.display_name,
            usage_type=group.usage_type,
            key_type=group.key_type,
            key_curve=group.key_curve,
            key_size=group.key_size,
            auto_rotate=auto_rotate,
            rotation_threshold_days=group.rotation_threshold_days,
            subject=group.subject,
        )
    except CertsApiClientError as exc:
        current_app.logger.exception(
            "Failed to update rotation setting",
            extra={"group_code": group_code},
        )
        flask_flash(_("Failed to update rotation setting: %(message)s", message=str(exc)), "error")
    else:
        flask_flash(_("Rotation setting updated."), "success")

    return redirect(url_for("certs_ui.group_detail", group_code=group_code))


@certs_ui_bp.route("/groups/<string:group_code>/issue", methods=["POST"])
@login_required
def issue_certificate(group_code: str):
    _ensure_permission()

    form = request.form
    subject_overrides = _build_subject_from_form(form)

    try:
        valid_days = _parse_int(form.get("valid_days"))
    except ValueError:
        flask_flash(_("Validity days must be a number."), "error")
        return redirect(url_for("certs_ui.group_detail", group_code=group_code))

    if form.get("unlimited_validity") == "on":
        valid_days = 0

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
        flask_flash(_("Failed to issue certificate: %(message)s", message=str(exc)), "error")
        return redirect(url_for("certs_ui.group_detail", group_code=group_code))

    flask_flash(_("Certificate issued successfully."), "success")
    session["certs_last_issued"] = {
        "kid": result.kid,
        "certificatePem": result.certificate_pem,
        "usageType": result.usage_type.value,
        "hasPrivateKey": bool(result.private_key_pem),
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
        flask_flash(_("Failed to revoke certificate: %(message)s", message=str(exc)), "error")
    else:
        flask_flash(_("Certificate revoked."), "success")

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
        flask_flash(_("Failed to load groups: %(message)s", message=str(exc)), "error")
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
            flask_flash(_("Invalid usage type specified."), "error")
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
            flask_flash(_("Invalid revoked flag."), "error")
            revoked = None

        def _parse_dt(value: str) -> datetime | None:
            if not value:
                return None
            try:
                return datetime.fromisoformat(value)
            except ValueError:
                flask_flash(_("Use ISO 8601 format for date filters."), "error")
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
            flask_flash(_("Failed to search certificates: %(message)s", message=str(exc)), "error")
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
        flask_flash(str(exc), "error")
        return redirect(url_for("certs_ui.index"))

    detail_context = {
        "certificate": certificate,
        "certificate_pem": certificate.certificate_pem.strip(),
        "not_before": certificate.not_before,
        "not_after": certificate.not_after,
        "subject": certificate.subject,
        "issuer": certificate.issuer,
        "jwk_json": json.dumps(certificate.jwk, indent=2, ensure_ascii=False),
        "key_usage_labels": dict(_KEY_USAGE_CHOICES),
        "extended_key_usage_labels": dict(_EXTENDED_KEY_USAGE_CHOICES),
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
        flask_flash(str(exc), "error")
        return redirect(url_for("certs_ui.index"))

    if request.method == "POST":
        reason = request.form.get("reason", "").strip() or None
        try:
            revoked = _service().revoke_certificate(kid, reason)
        except CertsApiClientError as exc:
            if exc.status_code == HTTPStatus.NOT_FOUND:
                abort(404)
            current_app.logger.exception("Failed to revoke certificate via API")
            flask_flash(str(exc), "error")
            return redirect(url_for("certs_ui.revoke", kid=kid))
        flask_flash(_("Certificate revoked."), "success")
        if next_url and next_url.startswith("/"):
            return redirect(next_url)
        return redirect(url_for("certs_ui.detail", kid=revoked.kid))

    return render_template("certs/revoke.html", certificate=certificate, next_url=next_url)
