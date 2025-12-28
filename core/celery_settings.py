"""Celery application configuration helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Sequence

from core.settings import settings


@dataclass(frozen=True)
class CelerySettings:
    """Immutable snapshot of Celery runtime configuration."""

    broker_url: str
    result_backend: str
    task_serializer: str = "json"
    result_serializer: str = "json"
    accept_content: Sequence[str] = field(default_factory=lambda: ["json"])
    timezone: str = "UTC"
    enable_utc: bool = True

    @classmethod
    def from_application_settings(cls) -> "CelerySettings":
        """Build settings using the shared application settings provider."""
        return cls(
            broker_url=settings.celery_broker_url,
            result_backend=settings.celery_result_backend,
            timezone=settings.babel_default_timezone or "UTC",
            enable_utc=True,
        )

    def as_mapping(self) -> Mapping[str, object]:
        """Expose the configuration using Celery's expected mapping format."""
        return {
            "broker_url": self.broker_url,
            "result_backend": self.result_backend,
            "task_serializer": self.task_serializer,
            "result_serializer": self.result_serializer,
            "accept_content": list(self.accept_content),
            "timezone": self.timezone,
            "enable_utc": self.enable_utc,
        }
