from datetime import datetime
import json
import secrets
from urllib.parse import urlencode

import requests
from flask import (
    current_app,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
    flash,
)
from flask_login import login_required
from flask_babel import gettext as _

from . import bp
from ..extensions import db
from ..models.google_account import GoogleAccount



