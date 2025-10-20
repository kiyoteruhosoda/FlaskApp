"""Helper utilities for structured logging within the web application."""

from __future__ import annotations

import base64
import binascii
import json
from typing import Any, Dict, List, Sequence

# Attribute name used on ``flask.g`` to cache the computed JWT trace payload.
JWT_TRACE_CACHE_ATTR = "_cached_jwt_trace_for_logging"


def _decode_segment(segment: str) -> Any:
    """Decode a base64url encoded JWT segment into JSON or text."""

    if not isinstance(segment, str):
        return "<non-string segment>"

    padded = segment + "=" * (-len(segment) % 4)
    try:
        decoded = base64.urlsafe_b64decode(padded.encode("ascii"))
    except (binascii.Error, ValueError):
        return "<invalid base64>"

    try:
        text = decoded.decode("utf-8")
    except UnicodeDecodeError:
        return "<binary segment>"

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def summarize_jwts(tokens: Sequence[str]) -> List[Dict[str, Any]]:
    """Return structured summaries for each JWT token in *tokens*."""

    summaries: List[Dict[str, Any]] = []
    for token in tokens:
        if not token or not isinstance(token, str):
            continue

        token_str = token.strip()
        if not token_str:
            continue

        parts = token_str.split(".")
        summary: Dict[str, Any] = {
            "token": token_str,
        }
        if len(token_str) > 64:
            summary["token_preview"] = f"{token_str[:32]}…{token_str[-16:]}"

        if len(parts) >= 2:
            summary["header"] = _decode_segment(parts[0])
            summary["claims"] = _decode_segment(parts[1])
        else:
            summary["error"] = "not a JWT"

        if len(parts) >= 3:
            signature = parts[2]
            summary["signature_preview"] = signature[:16] + ("…" if len(signature) > 16 else "")

        summaries.append(summary)

    return summaries


def build_jwt_trace(tokens: Sequence[str]) -> str | None:
    """Return a JSON string suitable for persisting in the log trace column."""

    summaries = summarize_jwts(tokens)
    if not summaries:
        return None
    return json.dumps(summaries, ensure_ascii=False, default=str)
