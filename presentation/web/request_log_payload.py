"""リクエスト/レスポンスを構造化ログへ書き出す際のペイロード整形を担う。

`create_app()` のリクエストフックに散在していたロジックをここへ集約する。
責務は「ログ用にデータを安全（機密マスク）かつ簡潔（サイズ・長さ制限）な
形へ変換すること」のみで、Flask のリクエストコンテキストには依存しない純粋
関数として実装する。これにより単体テストで網羅的に振る舞いを検証できる。
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, Dict, List, Tuple

from werkzeug.datastructures import FileStorage


SENSITIVE_KEYWORDS = {
    "password",
    "passwd",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
}

# 1リクエスト/レスポンスあたりのログ本文の上限バイト数。
MAX_LOG_PAYLOAD_BYTES = 60_000

# POSTパラメータ等の文字列値をログに残す際の最大長。
MAX_POST_PARAM_STRING_LENGTH = 120


def is_sensitive_key(key: Any) -> bool:
    """キー名が機密情報を示すかどうかを判定する。"""

    if not isinstance(key, str):
        return False
    key_lower = key.lower()
    return any(keyword in key_lower for keyword in SENSITIVE_KEYWORDS)


def mask_sensitive_data(data: Any) -> Any:
    """再帰的に辞書やリスト内の機密情報をマスクする。"""

    if isinstance(data, Mapping):
        masked = {}
        for key, value in data.items():
            if is_sensitive_key(key):
                masked[key] = "***"
            else:
                masked[key] = mask_sensitive_data(value)
        return masked
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        return [mask_sensitive_data(item) for item in data]
    return data


def summarize_for_logging(
    data: Any,
    *,
    _depth: int = 0,
    _max_depth: int = 2,
    _max_string_length: int = 120,
    _max_list_items: int = 1,
    _max_dict_items: int = 10,
) -> Any:
    """ログ用にJSONレスポンスを必要最小限の情報へ要約する。"""

    if data is None or isinstance(data, (bool, int, float)):
        return data

    if isinstance(data, str):
        if len(data) <= _max_string_length:
            return data
        return f"{data[:_max_string_length]}… ({len(data)} chars)"

    if isinstance(data, (bytes, bytearray)):
        return f"<binary {len(data)} bytes>"

    if _depth >= _max_depth:
        if isinstance(data, Mapping):
            keys = list(data.keys())
            summary = {
                "type": "dict",
                "keys": keys[:_max_dict_items],
                "length": len(keys),
            }
            if len(keys) > _max_dict_items:
                summary["..."] = f"{len(keys) - _max_dict_items} more keys"
            return summary
        if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
            return {
                "type": "list",
                "length": len(data),
            }
        return str(data)

    if isinstance(data, Mapping):
        summary = {}
        for index, (key, value) in enumerate(data.items()):
            if index >= _max_dict_items:
                summary["..."] = f"{len(data) - _max_dict_items} more keys"
                break
            summary[key] = summarize_for_logging(
                value,
                _depth=_depth + 1,
                _max_depth=_max_depth,
                _max_string_length=_max_string_length,
                _max_list_items=_max_list_items,
                _max_dict_items=_max_dict_items,
            )
        return summary

    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        length = len(data)
        summary = {"length": length}
        if length:
            sample_count = min(length, _max_list_items)
            summary["sample"] = [
                summarize_for_logging(
                    data[i],
                    _depth=_depth + 1,
                    _max_depth=_max_depth,
                    _max_string_length=_max_string_length,
                    _max_list_items=_max_list_items,
                    _max_dict_items=_max_dict_items,
                )
                for i in range(sample_count)
            ]
            if length > sample_count:
                summary["..."] = f"{length - sample_count} more items"
        return summary

    return str(data)


def serialize_for_logging(payload: Any) -> Tuple[str, int]:
    """ペイロードをJSON文字列化し、(文字列, UTF-8バイト長) を返す。"""

    text = json.dumps(payload, ensure_ascii=False, default=str)
    return text, len(text.encode("utf-8"))


def prepare_log_payload(
    payload: Dict[str, Any],
    *,
    keys_to_summarize: Sequence[str],
    max_bytes: int = MAX_LOG_PAYLOAD_BYTES,
) -> Tuple[Dict[str, Any], str]:
    """サイズ上限を超えるペイロードを段階的に要約・省略して上限内へ収める。"""

    working = dict(payload)
    text, size = serialize_for_logging(working)
    if size <= max_bytes:
        return working, text

    truncation: Dict[str, Dict[str, Any]] = {}
    existing_truncation = working.get("_truncation")
    if isinstance(existing_truncation, dict):
        truncation.update(existing_truncation)

    for key in keys_to_summarize:
        if key not in working:
            continue
        value = working[key]
        if value is None:
            continue
        summary = summarize_for_logging(value)
        if summary is value:
            continue

        _, value_size = serialize_for_logging(value)
        truncation[key] = {
            "summary": True,
            "originalBytes": value_size,
        }
        working[key] = summary
        working["_truncation"] = {"limitBytes": max_bytes, **truncation}

        text, size = serialize_for_logging(working)
        if size <= max_bytes:
            return working, text

    minimal: Dict[str, Any] = {
        "status": working.get("status"),
        "message": "payload omitted due to size limit",
        "_truncation": {"limitBytes": max_bytes, **truncation, "omitted": True},
    }

    text, size = serialize_for_logging(minimal)
    if size <= max_bytes:
        return minimal, text

    fallback = {
        "message": "payload omitted",
        "_truncation": {"limitBytes": max_bytes, "omitted": True},
    }
    fallback_text, _ = serialize_for_logging(fallback)
    return fallback, fallback_text


def truncate_long_parameter_values(value: Any) -> Any:
    """長すぎる文字列やバイナリ値を要約しつつ構造は保持する。"""

    if isinstance(value, Mapping):
        return {k: truncate_long_parameter_values(v) for k, v in value.items()}

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [truncate_long_parameter_values(item) for item in value]

    if isinstance(value, str):
        if len(value) <= MAX_POST_PARAM_STRING_LENGTH:
            return value
        return f"{value[:MAX_POST_PARAM_STRING_LENGTH]}… ({len(value)} chars)"

    if isinstance(value, (bytes, bytearray)):
        return f"<binary {len(value)} bytes>"

    return value


def format_form_parameters_for_logging(form) -> Dict[str, Any]:
    """フォーム（MultiDict）をログ用の辞書へ整形する。"""

    if not form:
        return {}

    result: Dict[str, Any] = {}
    for key in form.keys():
        values = form.getlist(key)
        summarized_values = [truncate_long_parameter_values(value) for value in values]
        if len(summarized_values) == 1:
            result[key] = summarized_values[0]
        else:
            result[key] = summarized_values
    return result


def summarize_file_storage(storage: FileStorage) -> Dict[str, Any]:
    """アップロードファイルは本文を残さず、メタ情報のみを要約する。"""

    summary: Dict[str, Any] = {"omitted": True}
    filename = getattr(storage, "filename", None)
    if filename:
        summary["filename"] = filename
    content_type = getattr(storage, "content_type", None)
    if content_type:
        summary["contentType"] = content_type
    content_length = getattr(storage, "content_length", None)
    if isinstance(content_length, int):
        summary["contentLength"] = content_length
    return summary


def format_file_parameters_for_logging(files) -> Dict[str, Any]:
    """アップロードファイル群（MultiDict）をログ用の辞書へ整形する。"""

    if not files:
        return {}

    result: Dict[str, Any] = {}
    for key in files.keys():
        storages: List[FileStorage] = files.getlist(key)
        summarized = [summarize_file_storage(storage) for storage in storages]
        if len(summarized) == 1:
            result[key] = summarized[0]
        else:
            result[key] = summarized
    return result
