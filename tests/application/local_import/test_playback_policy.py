from __future__ import annotations

import pytest

from features.photonest.application.local_import.file_importer import PlaybackFailurePolicy


@pytest.mark.parametrize(
    "note, expected",
    [
        ("ffmpeg_missing", True),
        ("FFMPEG_MISSING", True),
        ("ffmpeg_custom_error", True),
        ("playback_skipped", True),
        ("", False),
        ("unrelated", False),
    ],
)
def test_playback_policy_is_recoverable(note: str, expected: bool) -> None:
    policy = PlaybackFailurePolicy()

    assert policy.is_recoverable(note) is expected


@pytest.mark.parametrize(
    "note, expected",
    [
        ("ffmpeg_missing", True),
        ("FFMPEG_MISSING", True),
        ("playback_skipped", False),
        ("", False),
        (None, False),
    ],
)
def test_playback_policy_requires_session(note: str | None, expected: bool) -> None:
    policy = PlaybackFailurePolicy()

    assert policy.requires_session(note) is expected
