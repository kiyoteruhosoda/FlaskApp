"""Utilities for inspecting Celery task records stored in the database."""

from __future__ import annotations

import argparse
import json
from typing import List, Mapping, MutableMapping, Optional, Sequence, Tuple
from datetime import datetime, timezone

from sqlalchemy import func

from core.db import db
from core.models import CeleryTaskRecord, CeleryTaskStatus

# Statuses that represent work that has not been finalized yet.
PENDING_STATUSES: Tuple[CeleryTaskStatus, ...] = (
    CeleryTaskStatus.SCHEDULED,
    CeleryTaskStatus.QUEUED,
    CeleryTaskStatus.RUNNING,
)


def _normalize_datetime(value: Optional[datetime]) -> Optional[str]:
    """Return a human readable UTC timestamp string."""

    if value is None:
        return None

    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    else:
        value = value.astimezone(timezone.utc)
    return value.strftime("%Y-%m-%d %H:%M:%SZ")


def _truncate(text: str, max_length: int) -> str:
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def _json_snippet(data: Optional[Mapping[str, object]], *, max_length: int = 60) -> str:
    if not data:
        return "-"
    text = json.dumps(data, ensure_ascii=False, sort_keys=True)
    return _truncate(text, max_length)


def _format_object_identity(object_type: Optional[str], object_id: Optional[str]) -> str:
    if not object_type and not object_id:
        return "-"
    if not object_type:
        return f"?:{object_id}"
    if not object_id:
        return f"{object_type}:?"
    return f"{object_type}:{object_id}"


def parse_status_filters(
    status_values: Optional[Sequence[str]] = None,
    *,
    include_pending: bool = False,
) -> List[CeleryTaskStatus]:
    """Convert CLI status filters into :class:`CeleryTaskStatus` values."""

    statuses: List[CeleryTaskStatus] = []

    def _append(status: CeleryTaskStatus) -> None:
        if status not in statuses:
            statuses.append(status)

    if status_values:
        for raw in status_values:
            if raw is None:
                continue
            text = raw.strip()
            if not text:
                continue
            normalized = text.replace("-", "_").replace(" ", "_")
            try:
                status = CeleryTaskStatus[normalized.upper()]
            except KeyError as exc:
                for item in CeleryTaskStatus:
                    if normalized.lower() == item.value.lower():
                        status = item
                        break
                else:
                    valid = ", ".join(s.value for s in CeleryTaskStatus)
                    raise ValueError(
                        f"Unknown status '{raw}'. Valid values are: {valid}."
                    ) from exc
            _append(status)

    if include_pending:
        for status in PENDING_STATUSES:
            _append(status)

    return statuses


def _query_tasks(
    statuses: Optional[Sequence[CeleryTaskStatus]] = None,
    *,
    limit: Optional[int] = None,
) -> List[CeleryTaskRecord]:
    query = CeleryTaskRecord.query.order_by(
        CeleryTaskRecord.created_at.desc(),
        CeleryTaskRecord.id.desc(),
    )
    if statuses:
        query = query.filter(CeleryTaskRecord.status.in_(tuple(statuses)))
    if limit and limit > 0:
        query = query.limit(limit)
    return list(query)


def summarize_task_statuses() -> MutableMapping[str, int]:
    """Return a mapping of ``status -> count`` including totals."""

    results = (
        db.session.query(CeleryTaskRecord.status, func.count(CeleryTaskRecord.id))
        .group_by(CeleryTaskRecord.status)
        .all()
    )
    summary: MutableMapping[str, int] = {status.value: count for status, count in results}
    total = sum(summary.values())
    for status in CeleryTaskStatus:
        summary.setdefault(status.value, 0)
    summary["total"] = total
    return summary


def _record_to_dict(
    record: CeleryTaskRecord,
    *,
    include_payload: bool = False,
    include_result: bool = False,
) -> MutableMapping[str, object]:
    data: MutableMapping[str, object] = {
        "id": record.id,
        "task_name": record.task_name,
        "status": record.status.value,
        "object_type": record.object_type,
        "object_id": record.object_id,
        "celery_task_id": record.celery_task_id,
        "scheduled_for": _normalize_datetime(record.scheduled_for),
        "created_at": _normalize_datetime(record.created_at),
        "started_at": _normalize_datetime(record.started_at),
        "finished_at": _normalize_datetime(record.finished_at),
        "updated_at": _normalize_datetime(record.updated_at),
        "error_message": record.error_message,
    }
    if include_payload:
        data["payload"] = record.payload
    if include_result:
        data["result"] = record.result
    return data


def get_task_overview(
    statuses: Optional[Sequence[CeleryTaskStatus]] = None,
    *,
    limit: Optional[int] = None,
    include_payload: bool = False,
    include_result: bool = False,
) -> Tuple[MutableMapping[str, int], List[MutableMapping[str, object]]]:
    """Return summary information and serialized task rows."""

    records = _query_tasks(statuses, limit=limit)
    serialized = [
        _record_to_dict(
            record,
            include_payload=include_payload,
            include_result=include_result,
        )
        for record in records
    ]
    summary = summarize_task_statuses()
    return summary, serialized


def format_tasks_table(
    tasks: Sequence[Mapping[str, object]],
    *,
    include_payload: bool = False,
    include_result: bool = False,
) -> str:
    """Render task information as a text table suitable for terminals."""

    if not tasks:
        return "No Celery task records found for the specified filters."

    columns: List[Tuple[str, str]] = [
        ("id", "ID"),
        ("task_name", "Task"),
        ("status", "Status"),
        ("object", "Object"),
        ("celery_task_id", "Celery ID"),
        ("created_at", "Created"),
        ("scheduled_for", "Scheduled"),
        ("started_at", "Started"),
        ("finished_at", "Finished"),
        ("error_message", "Error"),
    ]
    if include_payload:
        columns.append(("payload", "Payload"))
    if include_result:
        columns.append(("result", "Result"))

    rows: List[List[str]] = []

    for task in tasks:
        row: List[str] = []
        for key, _header in columns:
            if key == "object":
                value = _format_object_identity(
                    task.get("object_type") if isinstance(task, Mapping) else None,
                    task.get("object_id") if isinstance(task, Mapping) else None,
                )
            elif key == "payload":
                value = _json_snippet(task.get("payload") if isinstance(task, Mapping) else None)
            elif key == "result":
                value = _json_snippet(task.get("result") if isinstance(task, Mapping) else None)
            else:
                raw = task.get(key) if isinstance(task, Mapping) else None
                if raw is None:
                    value = "-"
                else:
                    value = str(raw)
                    if key == "error_message":
                        value = _truncate(value, 80)
            row.append(value)
        rows.append(row)

    widths = [
        max(len(header), *(len(row[idx]) for row in rows)) for idx, (_key, header) in enumerate(columns)
    ]

    header_line = " | ".join(header.ljust(widths[idx]) for idx, (_key, header) in enumerate(columns))
    separator_line = "-+-".join("-" * widths[idx] for idx in range(len(columns)))
    data_lines = [
        " | ".join(row[idx].ljust(widths[idx]) for idx in range(len(columns))) for row in rows
    ]

    return "\n".join([header_line, separator_line, *data_lines])


def format_summary(summary: Mapping[str, int]) -> str:
    """Render a textual summary of task counts."""

    lines = ["Status summary:"]
    for status in CeleryTaskStatus:
        value = summary.get(status.value, 0)
        lines.append(f"  {status.value:>8}: {value}")
    total = summary.get("total", sum(summary.get(status.value, 0) for status in CeleryTaskStatus))
    lines.append(f"  {'total':>8}: {total}")
    return "\n".join(lines)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="List Celery task records stored in the application database.",
    )
    parser.add_argument(
        "-s",
        "--status",
        dest="statuses",
        action="append",
        help=(
            "Filter by task status. Can be provided multiple times. "
            "Accepts names like 'queued', 'running', 'success', etc."
        ),
    )
    parser.add_argument(
        "--pending",
        action="store_true",
        help="Include pending statuses (scheduled, queued, running).",
    )
    parser.add_argument(
        "-n",
        "--limit",
        type=int,
        default=50,
        help="Maximum number of task rows to include (default: 50). Use 0 for no limit.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of a formatted table.",
    )
    parser.add_argument(
        "--include-payload",
        action="store_true",
        help="Include payload details in the output.",
    )
    parser.add_argument(
        "--include-result",
        action="store_true",
        help="Include result details in the output.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)

    try:
        statuses = parse_status_filters(args.statuses, include_pending=args.pending)
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    limit = args.limit if args.limit and args.limit > 0 else None

    from webapp import create_app

    app = create_app()

    with app.app_context():
        summary, tasks = get_task_overview(
            statuses,
            limit=limit,
            include_payload=args.include_payload,
            include_result=args.include_result,
        )

    if args.json:
        payload = {
            "summary": summary,
            "tasks": tasks,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(format_summary(summary))
        print()
        print(format_tasks_table(
            tasks,
            include_payload=args.include_payload,
            include_result=args.include_result,
        ))
        if args.limit and args.limit > 0 and len(tasks) == args.limit:
            print(
                "\n(showing the most recent "
                f"{args.limit} tasks; use --limit to adjust or 0 for all records)"
            )
    return 0


if __name__ == "__main__":  # pragma: no cover - manual invocation
    raise SystemExit(main())
