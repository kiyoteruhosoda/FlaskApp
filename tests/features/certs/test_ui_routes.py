import pytest

from features.certs.presentation.ui import routes


def test_build_subject_from_form_accepts_valid_characters():
    form = {
        "subject_cn": "Example Co., Ltd.",
        "subject_o": "ACME@Corp",
        "subject_c": "JP",
    }

    subject = routes._build_subject_from_form(form)

    assert subject == {
        "CN": "Example Co., Ltd.",
        "O": "ACME@Corp",
        "C": "JP",
    }


def test_build_subject_from_form_rejects_invalid_characters():
    form = {
        "subject_cn": "Invalid<Subject>",
    }

    with pytest.raises(ValueError):
        routes._build_subject_from_form(form)
