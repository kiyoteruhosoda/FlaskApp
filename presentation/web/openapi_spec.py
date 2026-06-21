"""OpenAPI 仕様の後処理とサーバ URL 算出を担う。

`create_app()` 内に散在していた OpenAPI 関連ロジックをここへ集約する。
責務は次の2つに限定する:

1. 生成済み OpenAPI 仕様（apispec）への後処理
   （URL プレフィックスの除去、成功レスポンスの補完）。
2. リクエスト/設定から OpenAPI `servers` 用の URL を算出すること。

URL 文字列の正規化・結合は副作用のない純粋関数として実装し、単体テストで
網羅的に検証できるようにする。リクエスト依存の算出のみ Flask の `request` と
アプリ設定を参照する。
"""

from __future__ import annotations

from collections.abc import MutableMapping
from copy import deepcopy
from typing import List, Optional
from urllib.parse import urlsplit

from flask import request

from core.settings import settings


def normalize_openapi_prefix(prefix: Optional[str]) -> str:
    """OpenAPI のパスプレフィックスを先頭スラッシュ付き・末尾スラッシュ無しへ正規化する。"""

    if not prefix:
        return ""
    normalized = prefix.strip()
    if not normalized:
        return ""
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    # The OpenAPI server URL should not end with a trailing slash unless the prefix is root
    return normalized.rstrip("/")


def strip_openapi_path_prefix(spec, prefix: Optional[str]) -> None:
    """仕様内の各パスから共通プレフィックスを取り除く（servers 側へ寄せるため）。"""

    normalized_prefix = normalize_openapi_prefix(prefix)
    if not normalized_prefix:
        return
    paths = getattr(spec, "_paths", None)
    if not isinstance(paths, MutableMapping):
        return
    items = list(paths.items())
    if not items:
        return
    if not any(path.startswith(normalized_prefix) for path, _ in items):
        return
    new_paths = type(paths)()
    for path, operations in items:
        if path.startswith(normalized_prefix):
            trimmed = path[len(normalized_prefix) :]
            if not trimmed:
                trimmed = "/"
            elif not trimmed.startswith("/"):
                trimmed = f"/{trimmed}"
            new_paths[trimmed] = operations
        else:
            new_paths[path] = operations
    spec._paths = new_paths


def ensure_openapi_success_responses(spec) -> None:
    """2xx 応答が未定義のオペレーションに既定の成功レスポンスを補完する。"""

    if spec is None:
        return
    paths = getattr(spec, "_paths", None)
    if not isinstance(paths, MutableMapping):
        return
    default_response = {
        "description": "Successful response",
        "content": {
            "application/json": {
                "schema": {
                    "type": "object",
                    "required": ["result"],
                    "properties": {
                        "result": {
                            "type": "string",
                            "description": "Generic success indicator.",
                            "example": "OK",
                        }
                    },
                    "additionalProperties": False,
                }
            }
        },
    }
    for operations in paths.values():
        if not isinstance(operations, MutableMapping):
            continue
        for operation in operations.values():
            if not isinstance(operation, MutableMapping):
                continue
            responses = operation.setdefault("responses", {})
            if not isinstance(responses, MutableMapping):
                continue
            has_success = False
            for status_code in responses.keys():
                try:
                    code_int = int(status_code)
                except (TypeError, ValueError):
                    continue
                if 200 <= code_int < 300:
                    has_success = True
                    break
            if has_success:
                continue
            responses["200"] = deepcopy(default_response)


def normalize_script_root(script_root: Optional[str]) -> str:
    """WSGI の SCRIPT_ROOT を先頭スラッシュ付き・末尾スラッシュ無しへ正規化する。"""

    if not script_root:
        return ""
    normalized = script_root.strip()
    if not normalized:
        return ""
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    return normalized.rstrip("/")


def build_base_url(scheme: str, host: str, script_root: str) -> str:
    """スキーム・ホスト・スクリプトルートからベース URL を組み立てる。"""

    base = f"{scheme}://{host.strip()}"
    if script_root and script_root != "/":
        base = f"{base}{script_root}"
    return base


def combine_base_and_prefix(base: str, api_prefix: str) -> str:
    """ベース URL と API プレフィックスを重複なく結合する。"""

    normalized_base = base.rstrip("/") or ("/" if base.startswith("/") else base or "/")
    if not api_prefix:
        return normalized_base
    if normalized_base == "/":
        return api_prefix or "/"
    if normalized_base.endswith(api_prefix):
        return normalized_base
    return f"{normalized_base}{api_prefix}"


def calculate_openapi_server_urls(prefix: str) -> List[str]:
    """現在のリクエストとプロキシヘッダから OpenAPI `servers` 用 URL を算出する。"""

    script_root = normalize_script_root(request.script_root)

    host = (request.host or "").strip()
    if not host:
        host_url = request.host_url or ""
        if host_url:
            host = urlsplit(host_url).netloc
    if not host:
        url_root = request.url_root or ""
        if url_root:
            host = urlsplit(url_root).netloc
    host = host.strip()

    def add_url(urls: List[str], seen: set[str], base: str) -> None:
        if not base:
            return
        combined = combine_base_and_prefix(base, prefix)
        if combined in seen:
            return
        seen.add(combined)
        urls.append(combined)

    urls: List[str] = []
    seen: set[str] = set()

    schemes: List[str] = []

    def add_scheme(scheme: Optional[str]) -> None:
        if not scheme:
            return
        normalized = scheme.strip().lower()
        if normalized and normalized not in schemes:
            schemes.append(normalized)

    add_scheme(settings.preferred_url_scheme)

    forwarded_header = request.headers.get("Forwarded", "")
    if forwarded_header:
        for part in forwarded_header.split(","):
            for attribute in part.split(";"):
                attribute = attribute.strip()
                if attribute.lower().startswith("proto="):
                    value = attribute.split("=", 1)[1].strip().strip('"')
                    add_scheme(value)

    x_forwarded_proto = request.headers.get("X-Forwarded-Proto", "")
    if x_forwarded_proto:
        for proto in x_forwarded_proto.split(","):
            add_scheme(proto)

    add_scheme(request.scheme or request.environ.get("wsgi.url_scheme"))

    if not schemes:
        schemes = ["http"]

    if host:
        for scheme in schemes:
            base = build_base_url(scheme, host, script_root)
            add_url(urls, seen, base)

    if not urls:
        fallback = "/" if not prefix else prefix
        return [fallback]

    return urls
