# authz.py
from functools import wraps
from flask import abort, current_app
from flask_login import current_user, login_required

def require_roles(*role_names):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*a, **kw):
            if current_app.config.get('LOGIN_DISABLED'):
                return fn(*a, **kw)
            if not current_user.has_role(*role_names):
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco

def require_perms(*perm_codes):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*a, **kw):
            if current_app.config.get('LOGIN_DISABLED'):
                return fn(*a, **kw)
            scope = getattr(current_user, "scope", set())
            if not isinstance(scope, set):
                scope = set(scope)
            if not any(code in scope for code in perm_codes):
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco
