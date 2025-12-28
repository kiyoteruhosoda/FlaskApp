import pytest

from shared.domain.auth.principal import AuthenticatedPrincipal


def test_system_subject_appends_service_account_suffix():
    principal = AuthenticatedPrincipal(
        subject_type="system",
        subject_id="s+100",
        display_name="integration-runner",
    )

    assert principal.display_name == "integration-runner (sa)"


def test_system_subject_suffix_not_duplicated():
    principal = AuthenticatedPrincipal(
        subject_type="system",
        subject_id="s+101",
        display_name="integration-runner (sa)",
    )

    assert principal.display_name == "integration-runner (sa)"


@pytest.mark.parametrize(
    "attributes, expected",
    [
        ({"display_name": None, "name": "ci-bot"}, "ci-bot (sa)"),
        ({"display_name": None, "name": None}, "s+102 (sa)"),
    ],
)

def test_system_subject_suffix_applied_to_fallbacks(attributes, expected):
    principal = AuthenticatedPrincipal(
        subject_type="system",
        subject_id="s+102",
        name=attributes.get("name"),
        display_name=attributes.get("display_name"),
    )

    assert principal.display_name == expected
