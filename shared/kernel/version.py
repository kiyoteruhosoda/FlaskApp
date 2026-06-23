"""バージョン情報管理"""

import json
import logging
import os
from datetime import datetime

logger = logging.getLogger(__name__)

VERSION_FILE_PATH = os.path.join(os.path.dirname(__file__), "version.json")


def load_version_from_file():
    """バージョンファイルからバージョン情報を読み込み"""
    try:
        if os.path.exists(VERSION_FILE_PATH):
            with open(VERSION_FILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            logger.warning("Version file not found: %s", VERSION_FILE_PATH)
            return None
    except Exception as e:
        logger.warning("Failed to load version file: %s", e)
        return None


def get_default_version_info():
    """デフォルトのバージョン情報を取得"""
    return {
        "version": "dev",
        "commit_hash": "unknown",
        "branch": "unknown",
        "commit_date": "unknown",
        "build_date": datetime.now().isoformat(),
    }


def get_version_info():
    """バージョン情報を取得"""
    version_data = load_version_from_file()
    if version_data:
        version_data["app_start_date"] = datetime.now().isoformat()
        return version_data
    return get_default_version_info()


def get_version_string():
    """バージョン文字列を取得（短縮形）"""
    version_info = get_version_info()
    return version_info.get("version", "dev")
