
import os
from pathlib import Path

from flask import (
    Blueprint,
    render_template,
    flash,
    redirect,
    url_for,
    request,
    jsonify,
    session,
)
from ..extensions import db
from flask_login import login_required, current_user
from flask_babel import gettext as _

from core.models.user import User, Role, Permission
from core.models.service_account import ServiceAccount
from core.storage_paths import first_existing_storage_path, storage_path_candidates
from webapp.services.service_account_service import (
    ServiceAccountNotFoundError,
    ServiceAccountService,
    ServiceAccountValidationError,
)
from webapp.services.service_account_api_key_service import (
    ServiceAccountApiKeyNotFoundError,
    ServiceAccountApiKeyService,
    ServiceAccountApiKeyValidationError,
)


bp = Blueprint("admin", __name__, template_folder="templates")


# --- ここから各ルート定義 ---


# Permission helpers -----------------------------------------------------


def _can_manage_api_keys() -> bool:
    if not hasattr(current_user, "can"):
        return False
    return current_user.can("api_key:manage")


def _can_read_api_keys() -> bool:
    if not hasattr(current_user, "can"):
        return False
    if _can_manage_api_keys():
        return True
    return current_user.can("api_key:read")


# サービスアカウント管理
@bp.route("/service-accounts")
@login_required
def service_accounts():
    can_manage_accounts = current_user.can("service_account:manage")
    can_access_api_keys = _can_read_api_keys()

    if not (can_manage_accounts or can_access_api_keys):
        return _(u"You do not have permission to access this page."), 403

    accounts = [account.as_dict() for account in ServiceAccountService.list_accounts()]
    available_scopes = (
        sorted(current_user.permissions) if can_manage_accounts else []
    )
    return render_template(
        "admin/service_accounts.html",
        accounts=accounts,
        available_scopes=available_scopes,
        can_manage_accounts=can_manage_accounts,
        can_access_api_keys=can_access_api_keys,
    )


@bp.route("/service-accounts.json", methods=["GET"])
@login_required
def service_accounts_json():
    if not current_user.can("service_account:manage"):
        return jsonify({"error": "forbidden"}), 403

    accounts = [account.as_dict() for account in ServiceAccountService.list_accounts()]
    return jsonify({"items": accounts})


@bp.route("/service-accounts.json", methods=["POST"])
@login_required
def service_accounts_create():
    if not current_user.can("service_account:manage"):
        return jsonify({"error": "forbidden"}), 403

    payload = _extract_service_account_payload()
    try:
        account = ServiceAccountService.create_account(
            name=payload.get("name", ""),
            description=payload.get("description"),
            jwt_endpoint=payload.get("jwt_endpoint", ""),
            scope_names=payload.get("scope_names", ""),
            active=payload.get("active_flg", True),
            allowed_scopes=current_user.permissions,
        )
    except ServiceAccountValidationError as exc:
        response = {"error": exc.message}
        if exc.field:
            response["field"] = exc.field
        return jsonify(response), 400

    return jsonify({"item": account.as_dict()}), 201


@bp.route("/service-accounts/<int:account_id>.json", methods=["GET"])
@login_required
def service_accounts_detail(account_id: int):
    if not current_user.can("service_account:manage"):
        return jsonify({"error": "forbidden"}), 403

    account = ServiceAccount.query.get(account_id)
    if not account:
        return jsonify({"error": "not_found"}), 404
    return jsonify({"item": account.as_dict()})


@bp.route("/service-accounts/<int:account_id>.json", methods=["PUT", "PATCH"])
@login_required
def service_accounts_update(account_id: int):
    if not current_user.can("service_account:manage"):
        return jsonify({"error": "forbidden"}), 403

    payload = _extract_service_account_payload()
    try:
        account = ServiceAccountService.update_account(
            account_id,
            name=payload.get("name", ""),
            description=payload.get("description"),
            jwt_endpoint=payload.get("jwt_endpoint", ""),
            scope_names=payload.get("scope_names", ""),
            active=payload.get("active_flg", True),
            allowed_scopes=current_user.permissions,
        )
    except ServiceAccountNotFoundError:
        return jsonify({"error": "not_found"}), 404
    except ServiceAccountValidationError as exc:
        response = {"error": exc.message}
        if exc.field:
            response["field"] = exc.field
        return jsonify(response), 400

    return jsonify({"item": account.as_dict()})


@bp.route("/service-accounts/<int:account_id>.json", methods=["DELETE"])
@login_required
def service_accounts_delete(account_id: int):
    if not current_user.can("service_account:manage"):
        return jsonify({"error": "forbidden"}), 403

    try:
        ServiceAccountService.delete_account(account_id)
    except ServiceAccountNotFoundError:
        return jsonify({"error": "not_found"}), 404

    return jsonify({"status": "deleted"}), 200


@bp.route("/service-accounts/<int:account_id>/api-keys")
@login_required
def service_account_api_keys(account_id: int):
    if not _can_read_api_keys():
        return _(u"You do not have permission to access this page."), 403

    account = ServiceAccount.query.get(account_id)
    if not account:
        flash(_(u"The requested service account could not be found."), "warning")
        return redirect(url_for("admin.service_accounts"))

    try:
        key_records = ServiceAccountApiKeyService.list_keys(account_id)
    except ServiceAccountApiKeyNotFoundError:
        flash(_(u"The requested service account could not be found."), "warning")
        return redirect(url_for("admin.service_accounts"))
    except ServiceAccountApiKeyValidationError as exc:
        flash(exc.message, "danger")
        key_records = []

    account_dict = account.as_dict()
    account_dict["scopes"] = account.scopes
    account_dict["active"] = account.is_active()

    return render_template(
        "admin/service_account_api_keys.html",
        account=account_dict,
        initial_keys=[record.as_dict() for record in key_records],
        can_manage_api_keys=_can_manage_api_keys(),
    )


# Config表示ページ（管理者のみ）
@bp.route("/config")
@login_required
def show_config():
    if not (hasattr(current_user, 'has_role') and current_user.has_role("admin")):
        return _(u"You do not have permission to access this page."), 403
    # Only show public config values, not secrets
    from webapp.config import Config
    public_keys = [
        k for k in dir(Config)
        if not k.startswith("_") and k.isupper() and k not in ("SECRET_KEY")
    ]
    config_dict = {k: getattr(Config, k) for k in public_keys}
    return render_template("admin/config_view.html", config=config_dict)

# バージョン情報表示ページ（管理者のみ）
@bp.route("/version")
@login_required
def show_version():
    if not (hasattr(current_user, 'has_role') and current_user.has_role("admin")):
        return _(u"You do not have permission to access this page."), 403
    from core.version import get_version_info
    version_info = get_version_info()
    return render_template("admin/version_view.html", version_info=version_info)


@bp.route("/data-files")
@login_required
def show_data_files():
    if not current_user.can("system:manage"):
        return _(u"You do not have permission to access this page."), 403

    directory_definitions = [
        ("FPV_NAS_ORIGINALS_DIR", _("Original Media Directory")),
        ("FPV_NAS_THUMBS_DIR", _("Thumbnail Directory")),
        ("FPV_NAS_PLAY_DIR", _("Playback Directory")),
        ("LOCAL_IMPORT_DIR", _("Local Import Directory")),
    ]
    directory_keys = [config_key for config_key, _ in directory_definitions]
    selected_key = request.args.get("directory") or directory_keys[0]
    if selected_key not in directory_keys:
        selected_key = directory_keys[0]

    default_per_page = 50
    per_page = request.args.get("per_page", type=int) or default_per_page
    if per_page <= 0:
        per_page = default_per_page
    per_page = min(per_page, 500)

    per_page_options = [25, 50, 100, 200]
    if per_page not in per_page_options:
        per_page_select_options = sorted({*per_page_options, per_page})
    else:
        per_page_select_options = per_page_options

    filter_query = request.args.get("q", "").strip()
    page = request.args.get("page", type=int) or 1
    if page <= 0:
        page = 1

    directories: list[dict] = []
    selected_directory: dict | None = None

    for config_key, label in directory_definitions:
        candidates = storage_path_candidates(config_key)
        base_path = first_existing_storage_path(config_key)
        effective_base = base_path or (candidates[0] if candidates else None)
        exists = bool(effective_base and Path(effective_base).exists())

        summary = {
            "config_key": config_key,
            "label": label,
            "base_path": effective_base,
            "candidates": candidates,
            "exists": exists,
            "is_selected": config_key == selected_key,
        }
        directories.append(summary)

        if not summary["is_selected"]:
            continue

        selected_directory = dict(summary)
        selected_directory.update(
            {
                "files": [],
                "total_files": 0,
                "total_size_bytes": 0,
                "total_size_display": _format_bytes(0),
                "matching_size_bytes": 0,
                "matching_size_display": _format_bytes(0),
                "filter_active": bool(filter_query),
                "pagination": {
                    "page": page,
                    "per_page": per_page,
                    "total_pages": 1,
                    "total_matching": 0,
                    "start_index": 0,
                    "end_index": 0,
                    "has_prev": False,
                    "has_next": False,
                    "prev_url": None,
                    "next_url": None,
                    "first_url": None,
                    "last_url": None,
                    "pages": [],
                },
            }
        )

        if not (effective_base and exists):
            continue

        base_dir = Path(effective_base)
        total_files = 0
        total_size = 0
        matching_count = 0
        matching_size = 0
        page_files: list[dict] = []
        start_index = (page - 1) * per_page
        end_index = start_index + per_page
        lower_query = filter_query.lower()

        for rel_path, size in _iter_directory_entries(base_dir):
            total_files += 1
            total_size += size

            if lower_query and lower_query not in rel_path.lower():
                continue

            if start_index <= matching_count < end_index:
                page_files.append(
                    {
                        "name": rel_path,
                        "size_bytes": size,
                        "size_display": _format_bytes(size),
                    }
                )

            matching_count += 1
            matching_size += size

        if matching_count:
            total_pages = (matching_count + per_page - 1) // per_page
        else:
            total_pages = 1

        final_page = page
        if matching_count and page > total_pages:
            final_page = total_pages
            start_index = (final_page - 1) * per_page
            end_index = start_index + per_page
            page_files = []
            current_index = 0
            for rel_path, size in _iter_directory_entries(base_dir):
                if lower_query and lower_query not in rel_path.lower():
                    continue
                if start_index <= current_index < end_index:
                    page_files.append(
                        {
                            "name": rel_path,
                            "size_bytes": size,
                            "size_display": _format_bytes(size),
                        }
                    )
                current_index += 1

        if not matching_count:
            final_page = 1
            start_index = 0
            end_index = 0
        else:
            end_index = min(start_index + per_page, matching_count)

        base_query = {
            "directory": selected_key,
            "per_page": per_page,
        }
        if filter_query:
            base_query["q"] = filter_query

        pagination_pages = _build_pagination_pages(final_page, total_pages)
        pagination_page_links = [
            {
                "number": number,
                "url": url_for("admin.show_data_files", **base_query, page=number),
            }
            for number in pagination_pages
        ]

        pagination = {
            "page": final_page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_matching": matching_count,
            "start_index": start_index,
            "end_index": end_index,
            "has_prev": final_page > 1,
            "has_next": final_page < total_pages,
            "prev_url": url_for("admin.show_data_files", **base_query, page=final_page - 1)
            if final_page > 1
            else None,
            "next_url": url_for("admin.show_data_files", **base_query, page=final_page + 1)
            if final_page < total_pages
            else None,
            "first_url": url_for("admin.show_data_files", **base_query, page=1)
            if final_page > 1
            else None,
            "last_url": url_for("admin.show_data_files", **base_query, page=total_pages)
            if final_page < total_pages
            else None,
            "pages": pagination_page_links,
        }

        selected_directory.update(
            {
                "files": page_files,
                "total_files": total_files,
                "total_size_bytes": total_size,
                "total_size_display": _format_bytes(total_size),
                "matching_size_bytes": matching_size,
                "matching_size_display": _format_bytes(matching_size),
                "pagination": pagination,
            }
        )

    return render_template(
        "admin/data_files.html",
        directories=directories,
        selected_directory=selected_directory,
        filter_query=filter_query,
        per_page=per_page,
        per_page_options=per_page_select_options,
    )

# TOTPリセット
@bp.route("/user/<int:user_id>/reset-totp", methods=["POST"])
@login_required
def user_reset_totp(user_id):
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    # TOTPシークレットをリセット（Noneにする）
    user.totp_secret = None
    db.session.commit()
    flash(_("TOTP secret reset for user."), "success")
    return redirect(url_for("admin.user"))

# ユーザー削除
@bp.route("/user/<int:user_id>/delete", methods=["POST"])
@login_required
def user_delete(user_id):
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash(_("You cannot delete yourself."), "error")
        return redirect(url_for("admin.user"))
    db.session.delete(user)
    db.session.commit()
    flash(_("User deleted successfully."), "success")
    return redirect(url_for("admin.user"))

# ユーザーロール変更
@bp.route("/user/<int:user_id>/role", methods=["POST"])
@login_required
def user_change_role(user_id):
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    role_ids = request.form.getlist("roles")
    if not role_ids:
        flash(_("At least one role must be selected."), "error")
        return redirect(url_for("admin.user"))

    try:
        unique_role_ids = {int(role_id) for role_id in role_ids if role_id}
    except ValueError:
        flash(_("Invalid role selection."), "error")
        return redirect(url_for("admin.user"))

    if not unique_role_ids:
        flash(_("At least one role must be selected."), "error")
        return redirect(url_for("admin.user"))

    selected_roles = Role.query.filter(Role.id.in_(unique_role_ids)).all()
    if len(selected_roles) != len(unique_role_ids):
        flash(_("Selected role does not exist."), "error")
        return redirect(url_for("admin.user"))

    user.roles = selected_roles

    if user.id == current_user.id:
        active_role_id = session.get("active_role_id")
        selected_ids = {role.id for role in selected_roles}
        if active_role_id not in selected_ids:
            if len(selected_ids) == 1:
                session["active_role_id"] = selected_roles[0].id
            else:
                session.pop("active_role_id", None)
    db.session.commit()
    flash(_("User roles updated."), "success")
    return redirect(url_for("admin.user"))

# ユーザーのロール編集画面
@bp.route("/user/<int:user_id>/edit-roles", methods=["GET"])
@login_required
def user_edit_roles(user_id):
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    roles = Role.query.all()
    return render_template("admin/user_role_edit.html", user=user, roles=roles)

# ユーザー追加
@bp.route("/user/add", methods=["GET", "POST"])
@login_required
def user_add():
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    roles = Role.query.all()
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        role_id = request.form.get("role")
        if not email or not password or not role_id:
            flash(_("Email, password, and role are required."), "error")
            return render_template("admin/user_add.html", roles=roles)
        if User.query.filter_by(email=email).first():
            flash(_("Email already exists."), "error")
            return render_template("admin/user_add.html", roles=roles)
        role_obj = Role.query.get(int(role_id))
        if not role_obj:
            flash(_("Selected role does not exist."), "error")
            return render_template("admin/user_add.html", roles=roles)
        u = User(email=email)
        u.set_password(password)
        u.roles.append(role_obj)
        db.session.add(u)
        db.session.commit()
        flash(_("User created successfully."), "success")
        return redirect(url_for("admin.user"))
    return render_template("admin/user_add.html", roles=roles)


@bp.route("/user", methods=["GET"])
@login_required
def user():
    if not current_user.can('user:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    users = User.query.all()
    roles = Role.query.all()
    return render_template("admin/admin_users.html", users=users, roles=roles)


@bp.route("/permissions", methods=["GET"])
@login_required
def permissions():
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    search = request.args.get("search", "").strip()
    sort = request.args.get("sort", "id")
    order = request.args.get("order", "asc")

    query = Permission.query
    if search:
        query = query.filter(Permission.code.contains(search))

    if sort not in ["id", "code"]:
        sort = "id"
    sort_column = getattr(Permission, sort)
    if order == "desc":
        sort_column = sort_column.desc()
    else:
        sort_column = sort_column.asc()

    perms = query.order_by(sort_column).all()
    return render_template(
        "admin/permissions.html", permissions=perms, search=search, sort=sort, order=order
    )


@bp.route("/permissions/add", methods=["GET", "POST"])
@login_required
def permission_add():
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        code = request.form.get("code")
        if not code:
            flash(_("Code is required."), "error")
            return render_template("admin/permission_edit.html", permission=None)
        if Permission.query.filter_by(code=code).first():
            flash(_("Permission already exists."), "error")
            return render_template("admin/permission_edit.html", permission=None)
        p = Permission(code=code)
        db.session.add(p)
        db.session.commit()
        flash(_("Permission created successfully."), "success")
        return redirect(url_for("admin.permissions"))
    return render_template("admin/permission_edit.html", permission=None)


@bp.route("/permissions/<int:perm_id>/edit", methods=["GET", "POST"])
@login_required
def permission_edit(perm_id):
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    perm = Permission.query.get_or_404(perm_id)
    if request.method == "POST":
        code = request.form.get("code")
        if not code:
            flash(_("Code is required."), "error")
            return render_template("admin/permission_edit.html", permission=perm)
        perm.code = code
        db.session.commit()
        flash(_("Permission updated."), "success")
        return redirect(url_for("admin.permissions"))
    return render_template("admin/permission_edit.html", permission=perm)


@bp.route("/permissions/<int:perm_id>/delete", methods=["POST"])
@login_required
def permission_delete(perm_id):
    if not current_user.can('permission:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    perm = Permission.query.get_or_404(perm_id)
    db.session.delete(perm)
    db.session.commit()
    flash(_("Permission deleted."), "success")
    return redirect(url_for("admin.permissions"))


@bp.route("/roles", methods=["GET"])
@login_required
def roles():
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    roles = Role.query.all()
    return render_template("admin/roles.html", roles=roles)


@bp.route("/roles/add", methods=["GET", "POST"])
@login_required
def role_add():
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    permissions = Permission.query.all()
    if request.method == "POST":
        name = request.form.get("name")
        perm_ids = request.form.getlist("permissions")
        if not name:
            flash(_("Name is required."), "error")
            return render_template("admin/role_edit.html", role=None, permissions=permissions, selected=[])
        if Role.query.filter_by(name=name).first():
            flash(_("Role already exists."), "error")
            return render_template("admin/role_edit.html", role=None, permissions=permissions, selected=[])
        role = Role(name=name)
        for pid in perm_ids:
            perm = Permission.query.get(int(pid))
            if perm:
                role.permissions.append(perm)
        db.session.add(role)
        db.session.commit()
        flash(_("Role created successfully."), "success")
        return redirect(url_for("admin.roles"))
    return render_template("admin/role_edit.html", role=None, permissions=permissions, selected=[])


@bp.route("/roles/<int:role_id>/edit", methods=["GET", "POST"])
@login_required
def role_edit(role_id):
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    role = Role.query.get_or_404(role_id)
    permissions = Permission.query.all()
    if request.method == "POST":
        name = request.form.get("name")
        perm_ids = request.form.getlist("permissions")
        if not name:
            flash(_("Name is required."), "error")
            return render_template("admin/role_edit.html", role=role, permissions=permissions, selected=[p.id for p in role.permissions])
        role.name = name
        role.permissions = []
        for pid in perm_ids:
            perm = Permission.query.get(int(pid))
            if perm:
                role.permissions.append(perm)
        db.session.commit()
        flash(_("Role updated."), "success")
        return redirect(url_for("admin.roles"))
    selected = [p.id for p in role.permissions]
    return render_template("admin/role_edit.html", role=role, permissions=permissions, selected=selected)


@bp.route("/roles/<int:role_id>/delete", methods=["POST"])
@login_required
def role_delete(role_id):
    if not current_user.can('role:manage'):
        flash(_("You do not have permission to access this page."), "error")
        return redirect(url_for("index"))
    role = Role.query.get_or_404(role_id)
    db.session.delete(role)
    db.session.commit()
    flash(_("Role deleted."), "success")
    return redirect(url_for("admin.roles"))

# Google Accounts管理
@bp.route("/google-accounts", methods=["GET"])
@login_required
def google_accounts():
    from core.models.google_account import GoogleAccount

    # 管理者は全てのアカウントを表示、一般ユーザーは自分のアカウントのみ表示
    if current_user.can('user:manage'):
        accounts = GoogleAccount.query.all()
    else:
        accounts = GoogleAccount.query.filter_by(user_id=current_user.id).all()

    return render_template("admin/google_accounts.html", accounts=accounts)


def _extract_service_account_payload() -> dict:
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict()

    active_raw = data.get("active_flg", True)
    if isinstance(active_raw, str):
        active_value = active_raw.strip().lower() in {"1", "true", "on", "yes"}
    else:
        active_value = bool(active_raw)

    return {
        "name": data.get("name", ""),
        "description": data.get("description"),
        "jwt_endpoint": data.get("jwt_endpoint", ""),
        "scope_names": data.get("scope_names", ""),
        "active_flg": active_value,
    }


def _format_bytes(num: int) -> str:
    """人間が読みやすい形式にバイト数を整形."""

    step = 1024.0
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    value = float(num)
    for unit in units:
        if value < step or unit == units[-1]:
            if unit == "B":
                return f"{int(value)} {unit}"
            return f"{value:.1f} {unit}"
        value /= step
    return f"{value:.1f} PB"


def _iter_directory_entries(base_dir: Path):
    """指定ディレクトリ内のファイルをソートして列挙."""

    for root, dirs, filenames in os.walk(base_dir):
        dirs.sort()
        filenames.sort()
        for filename in filenames:
            file_path = Path(root) / filename
            try:
                size = file_path.stat().st_size
            except OSError:
                size = 0
            try:
                rel_path = file_path.relative_to(base_dir).as_posix()
            except ValueError:
                rel_path = file_path.as_posix()
            yield rel_path, size


def _build_pagination_pages(page: int, total_pages: int, window: int = 2) -> list[int]:
    """ページ番号の表示用リストを生成."""

    if total_pages <= 0:
        return [1]
    start = max(page - window, 1)
    end = min(page + window, total_pages)
    return list(range(start, end + 1))
