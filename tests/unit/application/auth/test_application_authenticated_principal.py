"""Unit tests for the application-level ``AuthenticatedPrincipal``.

Note: this covers ``shared.application.authenticated_principal`` (the immutable
snapshot used by the FastAPI layer), which is distinct from the domain-level
``shared.domain.auth.principal.AuthenticatedPrincipal``.
"""

from shared.application.authenticated_principal import AuthenticatedPrincipal


def test_user_id_aliases_subject_id_for_individual():
    principal = AuthenticatedPrincipal(
        subject_type="individual",
        subject_id=42,
        identifier="alice",
    )

    assert principal.user_id == 42
    assert principal.user_id == principal.id == principal.subject_id
    assert int(principal.user_id) == 42


def test_user_id_returns_subject_id_for_system_principal():
    principal = AuthenticatedPrincipal(
        subject_type="system",
        subject_id=7,
        identifier="service-runner",
        display_name="ci-bot",
    )

    assert principal.user_id == 7
    assert principal.user_id == principal.subject_id
