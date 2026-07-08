"""Tests for shared.application.auth.actor_utils."""
from __future__ import annotations

import pytest

from shared.application.auth import actor_utils


class _StubUser:
    def __init__(self, *, subject_id=None, identifier=None, display_name=None):
        self.subject_id = subject_id
        self._identifier = identifier
        self.display_name = display_name

    def get_id(self):
        return self._identifier


def test_subject_id_is_prioritized():
    user = _StubUser(subject_id="  user-subject  ", identifier="ignored", display_name="ignored")
    assert actor_utils.resolve_actor_identifier(user) == "user-subject"


def test_get_id_used_when_subject_missing():
    user = _StubUser(subject_id="  ", identifier="  login-id  ")
    assert actor_utils.resolve_actor_identifier(user) == "login-id"


def test_display_name_used_as_fallback():
    user = _StubUser(subject_id=None, identifier="", display_name="  Display Name  ")
    assert actor_utils.resolve_actor_identifier(user) == "Display Name"


def test_unknown_returned_when_no_identifier_available():
    user = _StubUser(subject_id="  ", identifier=None, display_name="  ")
    assert actor_utils.resolve_actor_identifier(user) == "unknown"
