import json
import json
from datetime import datetime
from typing import List

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session

from fpv.sync import run_sync
from core.db import db
from core.models.google_account import GoogleAccount
from core.models.job_sync import JobSync


def _setup_engine(with_account: bool = True):
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _connect(dbapi_connection, connection_record):
        dbapi_connection.create_function(
            "UTC_TIMESTAMP", 0, lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )

    db.Model.metadata.create_all(engine)

    if with_account:
        with Session(engine) as session:
            account = GoogleAccount(
                email="test@example.com",
                scopes="",
                status="active",
                oauth_token_json="{}",
            )
            session.add(account)
            session.commit()
    return engine


def _collect_events(output: str) -> List[str]:
    lines = [l for l in output.splitlines() if l.strip()]
    return [json.loads(l)["event"] for l in lines]


def test_run_sync_dry_run(monkeypatch, capsys):
    engine = _setup_engine(with_account=True)
    monkeypatch.setattr("fpv.sync.get_engine_from_env", lambda: engine)
    code = run_sync()
    assert code == 0
    out = capsys.readouterr().out
    events = _collect_events(out)
    assert events[0] == "sync.account.begin"
    assert events.count("sync.dryrun.item") == 3
    assert events[-2] == "sync.account.end"
    assert events[-1] == "sync.done"
    with Session(engine) as session:
        job = session.query(JobSync).one()
        assert job.status == "success"
        assert json.loads(job.stats_json) == {"listed": 3, "new": 0, "dup": 0, "failed": 0}


def test_run_sync_no_accounts(monkeypatch, capsys):
    engine = _setup_engine(with_account=False)
    monkeypatch.setattr("fpv.sync.get_engine_from_env", lambda: engine)
    code = run_sync()
    assert code == 0
    events = _collect_events(capsys.readouterr().out)
    assert events == ["sync.no_accounts"]
    with Session(engine) as session:
        rows = session.query(JobSync).all()
        assert rows == []
