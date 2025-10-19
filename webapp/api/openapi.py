"""OpenAPI helper utilities for documenting JSON request bodies."""
from __future__ import annotations

from typing import Any, Dict, Optional


def json_request_body(
    description: str,
    *,
    required: bool = True,
    schema: Optional[Dict[str, Any]] = None,
    example: Optional[Any] = None,
) -> Dict[str, Any]:
    """Create a requestBody block for JSON payloads.

    Args:
        description: Human readable description for Swagger UI.
        required: Whether the request body is required for the operation.
        schema: Optional JSON schema describing the expected payload structure.
        example: Optional example payload to display in Swagger UI.

    Returns:
        A dictionary compatible with Flask-Smorest's ``@bp.doc`` ``requestBody``
        parameter.
    """

    content_schema: Dict[str, Any]
    if schema is None:
        content_schema = {"type": "object", "additionalProperties": True}
    else:
        content_schema = schema

    content: Dict[str, Any] = {"application/json": {"schema": content_schema}}
    if example is not None:
        content["application/json"]["example"] = example

    return {
        "required": required,
        "description": description,
        "content": content,
    }
