"""`domain.local_import.media_metadata` のユーティリティに関するテスト。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from domain.local_import.media_metadata import extract_video_metadata


class _DummyCompletedProcess:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.returncode = 0
        self.stderr = ""


def _build_ffprobe_response(tags: dict[str, Any]) -> str:
    """テスト用のffprobe JSONレスポンス文字列を生成する。"""

    payload = {
        "streams": [
            {
                "codec_type": "video",
                "r_frame_rate": "30/1",
                "width": 1920,
                "height": 1080,
                "tags": tags,
            }
        ],
        "format": {"duration": "1.5", "tags": {}},
    }
    return json.dumps(payload)


def test_extract_video_metadata_uses_quicktime_creationdate_when_creation_time_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stream_tags に creation_time が無い場合でも撮影日時を取得できることを検証する。"""

    quicktime_value = "2024-08-18T12:34:56+09:00"

    def _fake_run(*_: Any, **__: Any) -> _DummyCompletedProcess:
        stdout = _build_ffprobe_response(
            {"com.apple.quicktime.creationdate": quicktime_value}
        )
        return _DummyCompletedProcess(stdout)

    monkeypatch.setattr(
        "domain.local_import.media_metadata.subprocess.run", _fake_run
    )

    metadata = extract_video_metadata("dummy.mov")

    assert metadata["creation_time"] == quicktime_value
    assert metadata["shot_at_raw"] == quicktime_value
    assert metadata["shot_at_source"] == "com.apple.quicktime.creationdate"
    assert metadata["shot_at"] == datetime(2024, 8, 18, 3, 34, 56, tzinfo=timezone.utc)
    assert metadata.get("stream_creation_time") is None


def test_extract_video_metadata_prefers_stream_creation_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """stream_tags に creation_time があればそれを優先して利用する。"""

    creation_time_value = "2023-05-11T09:08:07+00:00"

    def _fake_run(*_: Any, **__: Any) -> _DummyCompletedProcess:
        stdout = _build_ffprobe_response({"creation_time": creation_time_value})
        return _DummyCompletedProcess(stdout)

    monkeypatch.setattr(
        "domain.local_import.media_metadata.subprocess.run", _fake_run
    )

    metadata = extract_video_metadata("dummy.mov")

    assert metadata["creation_time"] == creation_time_value
    assert metadata["stream_creation_time"] == creation_time_value
    assert metadata["shot_at_raw"] == creation_time_value
    assert metadata["shot_at_source"] == "creation_time"
    assert metadata["shot_at"] == datetime(2023, 5, 11, 9, 8, 7, tzinfo=timezone.utc)


def test_extract_video_metadata_keeps_stream_creation_time_when_falling_back(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ストリームの creation_time がパースできない場合でも値を保持する。"""

    quicktime_value = "2022-01-02T03:04:05+09:00"

    def _fake_run(*_: Any, **__: Any) -> _DummyCompletedProcess:
        stdout = _build_ffprobe_response(
            {
                "creation_time": "not-a-date",
                "com.apple.quicktime.creationdate": quicktime_value,
            }
        )
        return _DummyCompletedProcess(stdout)

    monkeypatch.setattr(
        "domain.local_import.media_metadata.subprocess.run", _fake_run
    )

    metadata = extract_video_metadata("dummy.mov")

    assert metadata["stream_creation_time"] == "not-a-date"
    assert metadata["creation_time"] == quicktime_value
    assert metadata["shot_at_raw"] == quicktime_value
    assert metadata["shot_at_source"] == "com.apple.quicktime.creationdate"
    assert metadata["shot_at"] == datetime(2022, 1, 1, 18, 4, 5, tzinfo=timezone.utc)
