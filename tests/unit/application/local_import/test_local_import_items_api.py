"""`/api/local-import/sessions/<id>/items` エンドポイントの単体テスト。

認証ミドルウェアを介さずビュー関数を直接呼び、ファイル単位の取り込み状態を
返すロジックを検証する。
"""

from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.integration

from core.db import db
from core.models.picker_session import PickerSession
from core.models.photo_models import PickerSelection
from bounded_contexts.photonest.presentation.local_import_status_api import (
    get_session_items,
)


def _seed_session():
    session = PickerSession(status="processing")
    db.session.add(session)
    db.session.commit()

    rows = [
        PickerSelection(
            session_id=session.id,
            local_file_path="/import/ok.jpg",
            local_filename="ok.jpg",
            status="imported",
            attempts=1,
        ),
        PickerSelection(
            session_id=session.id,
            local_file_path="/import/bad.mov",
            local_filename="bad.mov",
            status="failed",
            attempts=3,
            error_msg="ffprobe failed",
        ),
        PickerSelection(
            session_id=session.id,
            local_file_path="/import/dup.jpg",
            local_filename="dup.jpg",
            status="dup",
            attempts=1,
        ),
    ]
    db.session.add_all(rows)
    db.session.commit()
    return session


def _json(response):
    # flask の Response / (body, status) いずれでも JSON を取り出す。
    if isinstance(response, tuple):
        response = response[0]
    return json.loads(response.get_data(as_text=True))


@pytest.mark.usefixtures("app_context")
def test_items_endpoint_lists_files_with_status_and_error():
    app = pytest.importorskip("flask").current_app
    session = _seed_session()

    with app.test_request_context(
        f"/api/local-import/sessions/{session.id}/items"
    ):
        payload = _json(get_session_items(session.id))

    assert payload["session_id"] == session.id
    assert payload["total_count"] == 3
    assert payload["status_counts"] == {"imported": 1, "failed": 1, "dup": 1}
    assert payload["returned_count"] == 3

    by_name = {item["filename"]: item for item in payload["items"]}
    assert by_name["bad.mov"]["status"] == "failed"
    assert by_name["bad.mov"]["error_msg"] == "ffprobe failed"
    assert by_name["bad.mov"]["attempts"] == 3
    assert by_name["ok.jpg"]["status"] == "imported"
    # item_id は /items/<item_id>/logs と突き合わせられる文字列。
    assert by_name["ok.jpg"]["item_id"] == str(by_name["ok.jpg"]["id"])


@pytest.mark.usefixtures("app_context")
def test_items_endpoint_filters_by_status():
    app = pytest.importorskip("flask").current_app
    session = _seed_session()

    with app.test_request_context(
        f"/api/local-import/sessions/{session.id}/items?status=failed"
    ):
        payload = _json(get_session_items(session.id))

    # フィルタしても集計はセッション全体を返す。
    assert payload["total_count"] == 3
    assert payload["returned_count"] == 1
    assert payload["items"][0]["filename"] == "bad.mov"


@pytest.mark.usefixtures("app_context")
def test_items_endpoint_404_for_missing_session():
    app = pytest.importorskip("flask").current_app
    with app.test_request_context("/api/local-import/sessions/999999/items"):
        with pytest.raises(Exception):
            get_session_items(999999)
