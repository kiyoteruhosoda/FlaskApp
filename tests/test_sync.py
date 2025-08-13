import json
from datetime import datetime
from typing import List

from sqlalchemy import create_engine, text, event

from fpv.sync import run_sync


def _setup_engine(with_account: bool = True):
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _connect(dbapi_connection, connection_record):
        dbapi_connection.create_function(
            "UTC_TIMESTAMP", 0, lambda: datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        )

    with engine.begin() as conn:
        conn.execute(text(
            """
            CREATE TABLE google_account (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                account_email TEXT,
                oauth_token_json TEXT,
                status TEXT
            )
            """
        ))
        conn.execute(text(
            """
            CREATE TABLE job_sync (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                target TEXT,
                account_id INTEGER,
                started_at TEXT,
                finished_at TEXT,
                status TEXT,
                stats_json TEXT
            )
            """
        ))
        if with_account:
            conn.execute(text(
                "INSERT INTO google_account (account_email, oauth_token_json, status) "
                "VALUES ('test@example.com', '{}', 'active')"
            ))
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
    with engine.connect() as conn:
        row = conn.execute(text("SELECT status, stats_json FROM job_sync")).fetchone()
        assert row[0] == "success"
        assert json.loads(row[1]) == {"new": 3, "dup": 0, "failed": 0}


def test_run_sync_no_accounts(monkeypatch, capsys):
    engine = _setup_engine(with_account=False)
    monkeypatch.setattr("fpv.sync.get_engine_from_env", lambda: engine)
    code = run_sync()
    assert code == 0
    events = _collect_events(capsys.readouterr().out)
    assert events == ["sync.no_accounts"]
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM job_sync")).fetchall()
        assert rows == []
