from __future__ import annotations
from typing import Tuple, Dict, Any, Optional, List
import base64, json, os, time
import httpx
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

TOKEN_URL = "https://oauth2.googleapis.com/token"
PHOTOS_BASE = "https://photoslibrary.googleapis.com/v1"
UA = "PhotoNest/0.1 (fpv)"


class ReauthRequired(Exception):
    """invalid_grant 等、再認証が必要な場合に投げる"""


def _key_from_env(oauth_key: str) -> bytes:
    if not oauth_key:
        raise ValueError("FPV_OAUTH_KEY 未設定")
    if oauth_key.startswith("base64:"):
        raw = base64.b64decode(oauth_key.split(":", 1)[1], validate=True)
    else:
        raw = oauth_key.encode("utf-8")
    if len(raw) != 32:
        raise ValueError(f"FPV_OAUTH_KEY 長さ不正: {len(raw)} bytes (要求: 32)")
    return raw


def _decrypt_envelope(oauth_token_json_enc: str, key: bytes) -> Dict[str, Any]:
    """
    期待するエンベロープ形式:
    {
      "alg": "AES-256-GCM",
      "nonce": "<b64>",
      "ct": "<b64>",
      "aad": "<optional b64>"
    }
    戻り値は復号したJSON(dict)。
    """
    env = json.loads(oauth_token_json_enc)
    if not isinstance(env, dict) or env.get("alg") != "AES-256-GCM":
        raise ValueError("not envelope")
    nonce = base64.b64decode(env["nonce"])
    ct = base64.b64decode(env["ct"])
    aad = base64.b64decode(env["aad"]) if env.get("aad") else None
    aes = AESGCM(key)
    pt = aes.decrypt(nonce, ct, aad)
    return json.loads(pt.decode("utf-8"))


def parse_oauth_payload(oauth_token_json_enc: str, oauth_key: str) -> Dict[str, Any]:
    """
    1) AES-GCM envelope を試す
    2) 失敗したら 平文JSON を試す（開発初期の利便性のため）
    """
    key = _key_from_env(oauth_key)
    try:
        return _decrypt_envelope(oauth_token_json_enc, key)
    except Exception:
        pass
    try:
        plain = json.loads(oauth_token_json_enc)
        if not isinstance(plain, dict):
            raise ValueError
        return plain
    except Exception as e:
        raise ValueError(
            "oauth_token_json の形式が不正です（envelope/平文JSON いずれも解釈不可）"
        ) from e


def refresh_access_token(
    oauth_token_json_enc: str,
    oauth_key: str,
    client_id: str,
    client_secret: str,
    timeout_sec: float = 15.0,
    max_retries: int = 3,
) -> Tuple[str, Dict[str, Any]]:
    """
    Returns: (access_token, meta)
      meta = { "expires_in": int, "token_type": str, "scope": str, "raw": dict }
    """
    payload = parse_oauth_payload(oauth_token_json_enc, oauth_key)
    refresh_token = payload.get("refresh_token")
    if not refresh_token:
        raise ValueError("refresh_token が存在しません")

    last_err: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            with httpx.Client(timeout=timeout_sec, headers={"User-Agent": UA}) as client:
                res = client.post(
                    TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "refresh_token": refresh_token,
                        "client_id": client_id,
                        "client_secret": client_secret,
                    },
                )
            if res.status_code == 400 and res.headers.get("content-type", "").startswith("application/json"):
                data = res.json()
                err = (data.get("error") or "").lower()
                if err == "invalid_grant":
                    raise ReauthRequired("invalid_grant: refresh_token が無効/取り消し")
            res.raise_for_status()
            data = res.json()
            access = data["access_token"]
            meta = {
                "expires_in": int(data.get("expires_in", 0)),
                "token_type": data.get("token_type"),
                "scope": data.get("scope"),
                "raw": data,
            }
            return access, meta
        except ReauthRequired:
            raise
        except Exception as e:
            last_err = e
            time.sleep(min(2 ** attempt, 8))
    assert last_err is not None
    raise last_err


def list_media_items_once(
    access_token: str,
    page_size: int = 100,
    page_token: Optional[str] = None,
    timeout_sec: float = 20.0,
) -> Dict[str, Any]:
    """
    1ページだけ取得して返す。
    Returns: { "mediaItems": [...], "nextPageToken": "..."? }
    """
    headers = {"Authorization": f"Bearer {access_token}", "User-Agent": UA}
    params = {"pageSize": page_size}
    if page_token:
        params["pageToken"] = page_token
    url = f"{PHOTOS_BASE}/mediaItems"
    with httpx.Client(timeout=timeout_sec, headers=headers) as client:
        r = client.get(url, params=params)
    r.raise_for_status()
    return r.json()
