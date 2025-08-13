from __future__ import annotations
from typing import Tuple, Dict, Any
import json

# 将来: httpxで実装。今回は呼び出しません（dry-run）
def refresh_access_token(oauth_token_json_enc: str, oauth_key: str) -> Tuple[str, Dict[str, Any]]:
    """
    Returns: (access_token, meta)
    - ここでは未実装。次ステップで暗号復号＆tokenエンドポイント呼び出しを実装する。
    """
    raise NotImplementedError("refresh_access_token is not implemented yet")
