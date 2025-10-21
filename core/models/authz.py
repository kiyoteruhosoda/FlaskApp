# authz.py
from functools import wraps
from flask import abort
from flask_login import current_user, login_required

from core.settings import settings

def require_perms(*perm_codes):
    def deco(fn):
        @wraps(fn)
        @login_required
        def wrapper(*a, **kw):
            if settings.login_disabled:
                return fn(*a, **kw)
            if not current_user.can(*perm_codes):
                abort(403)
            return fn(*a, **kw)
        return wrapper
    return deco
