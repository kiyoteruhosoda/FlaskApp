"""証明書自動ローテーションCeleryタスク"""
from __future__ import annotations

import logging
from typing import Any

from cli.src.celery.celery_app import celery
from features.certs.application.rotation import (
    AutoRotateCertificatesUseCase,
    RotationResult,
    RotationStatus,
)

logger = logging.getLogger("celery.task.certificates")


def _result_to_dict(result: RotationResult) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "groupCode": result.group.group_code,
        "status": result.status.value,
    }
    if result.certificate is not None:
        payload["kid"] = result.certificate.kid
        payload["expiresAt"] = (
            result.certificate.expires_at.isoformat() if result.certificate.expires_at else None
        )
    if result.reason:
        payload["reason"] = result.reason
    if result.private_key_pem:
        payload["privateKeyPem"] = result.private_key_pem
    if result.public_key_pem:
        payload["publicKeyPem"] = result.public_key_pem
    return payload


@celery.task(bind=True, name="certificates.auto_rotate")
def auto_rotate_certificates_task(self):
    """証明書グループのポリシーに基づき自動ローテーションを実施する"""

    use_case = AutoRotateCertificatesUseCase()
    results = use_case.execute()

    summary = [_result_to_dict(item) for item in results]

    rotated_count = sum(1 for item in results if item.status == RotationStatus.ROTATED)
    skipped_count = sum(1 for item in results if item.status == RotationStatus.SKIPPED)
    error_count = sum(1 for item in results if item.status == RotationStatus.ERROR)

    logger.info(
        "certificate rotation finished",
        extra={
            "event": "certificates.auto_rotate",
            "rotated": rotated_count,
            "skipped": skipped_count,
            "errors": error_count,
        },
    )

    return {
        "rotated": rotated_count,
        "skipped": skipped_count,
        "errors": error_count,
        "results": summary,
    }


__all__ = ["auto_rotate_certificates_task"]
