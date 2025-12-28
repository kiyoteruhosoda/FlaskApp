"""インポートアプリケーションサービス."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from .commands import ImportCommand
from .policy import ImportPolicy
from .results import ImportResult
from .template import AbstractImporter


@dataclass(slots=True)
class ImportApplicationService:
    """ユースケース全体を調整するアプリケーションサービス."""

    policy: ImportPolicy
    importers: Dict[str, AbstractImporter]
    logger: Any = field(repr=False)

    def execute(self, command: ImportCommand) -> ImportResult:
        self.policy.enforce(command)
        importer = self.importers.get(command.source)
        if not importer:
            raise ValueError(f"インポート戦略が見つかりません: {command.source}")

        self.logger.debug("import.usecase.dispatch", extra={"source": command.source})
        result = importer.execute(command)
        self.logger.info(
            "import.usecase.completed",
            extra={
                "source": command.source,
                "result": result.to_dict(),
            },
        )
        return result


__all__ = ["ImportApplicationService"]
