import base64
import io
from typing import Optional

import pyotp
import qrcode
from flask_babel import gettext as _

def new_totp_secret():
    return pyotp.random_base32()

def provisioning_uri(email: str, secret: str, issuer: Optional[str] = None):
    if issuer is None:
        issuer = _("AppName")
    return pyotp.totp.TOTP(secret).provisioning_uri(name=email, issuer_name=issuer)

def verify_totp(secret: str, token: str, valid_window: int = 1):
    # valid_windowで前後コードを許容（時刻ズレ許容）
    totp = pyotp.TOTP(secret)
    return totp.verify(token, valid_window=valid_window)


def qr_code_data_uri(uri: str) -> str:
    """Provisioning URI から QR コードの data URI を生成"""
    img = qrcode.make(uri)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    b64 = base64.b64encode(buf.getvalue()).decode()
    return f"data:image/png;base64,{b64}"
