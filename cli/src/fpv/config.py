from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Any

from dotenv import load_dotenv
from core.crypto import validate_oauth_key as _validate_oauth_key

# Load .env at import time so CLI and tests pick it up
load_dotenv()


# ---------------------------------------------------------------------------
# helpers


def _mask(val: str, keep: int = 4) -> str:
    if val is None:
        return ""
    if len(val) <= keep * 2:
        return "*" * len(val)
    return f"{val[:keep]}***{val[-keep:]}"


def _read_bool(env: Dict[str, str], key: str, default: bool = False) -> bool:
    raw = env.get(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _read_int(
    env: Dict[str, str], key: str, default: int, min_v: int, max_v: int
) -> Tuple[int, List[str]]:
    msgs: List[str] = []
    raw = env.get(key)
    if raw is None or raw.strip() == "":
        return default, msgs
    try:
        v = int(raw)
        if v < min_v or v > max_v:
            msgs.append(
                f"{key}: out of range ({v}), allowed {min_v}..{max_v} -> using default {default}"
            )
            return default, msgs
        return v, msgs
    except ValueError:
        msgs.append(
            f"{key}: could not parse as integer -> using default {default}"
        )
        return default, msgs


def _is_abs(p: str) -> bool:
    try:
        return Path(p).is_absolute()
    except Exception:
        return False


@dataclass(frozen=True)
class PhotoNestConfig:
    db_url: str
    nas_orig_dir: str
    nas_play_dir: str
    nas_thumbs_dir: str
    tmp_dir: str
    transcode_workers: int
    transcode_crf: int
    max_retries: int
    google_client_id: str
    google_client_secret: str
    oauth_key: str
    strict_path_check: bool

    # ------------------------------------------------------------------
    @staticmethod
    def from_env(env: Dict[str, str] | None = None) -> "PhotoNestConfig":
        env = env or os.environ

        db_url = env.get("FPV_DB_URL") or env.get("DATABASE_URI", "")
        db_url = db_url.strip()
        nas_orig = env.get("FPV_NAS_ORIG_DIR", "").strip()
        nas_play = env.get("FPV_NAS_PLAY_DIR", "").strip()
        nas_thumbs = env.get("FPV_NAS_THUMBS_DIR", "").strip()
        tmp_dir = env.get("FPV_TMP_DIR", "").strip()
        g_id = env.get("FPV_GOOGLE_CLIENT_ID") or env.get("GOOGLE_CLIENT_ID", "")
        g_id = g_id.strip()
        g_secret = env.get("FPV_GOOGLE_CLIENT_SECRET") or env.get(
            "GOOGLE_CLIENT_SECRET", ""
        )
        g_secret = g_secret.strip()

        if env.get("FPV_OAUTH_KEY"):
            oauth_key = env.get("FPV_OAUTH_KEY", "").strip()
        elif env.get("OAUTH_TOKEN_KEY"):
            oauth_key = env.get("OAUTH_TOKEN_KEY", "").strip()
        elif env.get("OAUTH_TOKEN_KEY_FILE"):
            try:
                with open(env.get("OAUTH_TOKEN_KEY_FILE"), "r") as f:
                    oauth_key = f.read().strip()
            except OSError:
                oauth_key = ""
        else:
            oauth_key = ""

        workers, _ = _read_int(env, "FPV_TRANSCODE_WORKERS", 2, 1, 8)
        crf, _ = _read_int(env, "FPV_TRANSCODE_CRF", 20, 10, 28)
        retries, _ = _read_int(env, "FPV_MAX_RETRIES", 3, 1, 10)

        strict = _read_bool(env, "FPV_STRICT_PATH_CHECK", False)

        return PhotoNestConfig(
            db_url=db_url,
            nas_orig_dir=nas_orig,
            nas_play_dir=nas_play,
            nas_thumbs_dir=nas_thumbs,
            tmp_dir=tmp_dir,
            transcode_workers=workers,
            transcode_crf=crf,
            max_retries=retries,
            google_client_id=g_id,
            google_client_secret=g_secret,
            oauth_key=oauth_key,
            strict_path_check=strict,
        )

    # ------------------------------------------------------------------
    def validate(self) -> Tuple[List[str], List[str]]:
        """Returns ``(warnings, errors)``"""
        warns: List[str] = []
        errs: List[str] = []

        required = {
            "FPV_DB_URL": self.db_url,
            "FPV_NAS_ORIG_DIR": self.nas_orig_dir,
            "FPV_NAS_PLAY_DIR": self.nas_play_dir,
            "FPV_NAS_THUMBS_DIR": self.nas_thumbs_dir,
            "FPV_TMP_DIR": self.tmp_dir,
            "FPV_GOOGLE_CLIENT_ID": self.google_client_id,
            "FPV_GOOGLE_CLIENT_SECRET": self.google_client_secret,
            "FPV_OAUTH_KEY": self.oauth_key,
        }

        for k, v in required.items():
            if not v:
                errs.append(f"{k}: not set")

        if self.db_url and not self.db_url.startswith("mysql+pymysql://"):
            warns.append("FPV_DB_URL: recommended scheme is mysql+pymysql://")

        for key, path in [
            ("FPV_NAS_ORIG_DIR", self.nas_orig_dir),
            ("FPV_NAS_PLAY_DIR", self.nas_play_dir),
            ("FPV_NAS_THUMBS_DIR", self.nas_thumbs_dir),
            ("FPV_TMP_DIR", self.tmp_dir),
        ]:
            if path and not _is_abs(path):
                errs.append(f"{key}: specify an absolute path (current: {path})")
            if self.strict_path_check and path and not Path(path).exists():
                errs.append(
                    f"{key}: path does not exist (strict-path-check enabled): {path}"
                )

        ok, why = _validate_oauth_key(self.oauth_key)
        if not ok:
            errs.append(f"FPV_OAUTH_KEY: invalid ({why})")

        if not (1 <= self.transcode_workers <= 8):
            errs.append("FPV_TRANSCODE_WORKERS: out of range 1..8")
        if not (10 <= self.transcode_crf <= 28):
            errs.append("FPV_TRANSCODE_CRF: out of range 10..28")
        if not (1 <= self.max_retries <= 10):
            errs.append("FPV_MAX_RETRIES: out of range 1..10")

        return warns, errs

    # ------------------------------------------------------------------
    def masked(self) -> Dict[str, Any]:
        return {
            "db_url": self.db_url,
            "nas_orig_dir": self.nas_orig_dir,
            "nas_play_dir": self.nas_play_dir,
            "nas_thumbs_dir": self.nas_thumbs_dir,
            "tmp_dir": self.tmp_dir,
            "transcode_workers": self.transcode_workers,
            "transcode_crf": self.transcode_crf,
            "max_retries": self.max_retries,
            "google_client_id": _mask(self.google_client_id),
            "google_client_secret": _mask(self.google_client_secret),
            "oauth_key": _mask(self.oauth_key),
            "strict_path_check": self.strict_path_check,
        }

