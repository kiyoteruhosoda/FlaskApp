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


@pytest.fixture
def set_current_user(monkeypatch):
    def _apply(user):
        monkeypatch.setattr(actor_utils, "current_user", user, raising=False)

    return _apply


def test_subject_id_is_prioritized(set_current_user):
    user = _StubUser(subject_id="  user-subject  ", identifier="ignored", display_name="ignored")
    set_current_user(user)

    assert actor_utils.resolve_actor_identifier() == "user-subject"


def test_get_id_used_when_subject_missing(set_current_user):
    user = _StubUser(subject_id="  ", identifier="  login-id  ")
    set_current_user(user)

    assert actor_utils.resolve_actor_identifier() == "login-id"


def test_display_name_used_as_fallback(set_current_user):
    user = _StubUser(subject_id=None, identifier="", display_name="  Display Name  ")
    set_current_user(user)

    assert actor_utils.resolve_actor_identifier() == "Display Name"


def test_unknown_returned_when_no_identifier_available(set_current_user):
    user = _StubUser(subject_id="  ", identifier=None, display_name="  ")
    set_current_user(user)

    assert actor_utils.resolve_actor_identifier() == "unknown"
