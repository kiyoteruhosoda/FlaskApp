from __future__ import annotations
import json, sys, time, uuid
from typing import Any, Dict


def log(event: str, **fields: Any) -> None:
    rec: Dict[str, Any] = {
        "event": event,
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    rec.update(fields)
    sys.stdout.write(json.dumps(rec, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]
