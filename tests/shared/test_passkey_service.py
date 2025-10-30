import json
from dataclasses import dataclass, field
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest

from shared.application.passkey_service import (
    PasskeyAuthenticationError,
    PasskeyRegistrationError,
    PasskeyService,
)
from webauthn.helpers import bytes_to_base64url


@dataclass
class StubCredential:
    credential_id: str


@dataclass
class StubRepository:
    credentials: list[StubCredential] = field(default_factory=list)
    added_records: list[dict] = field(default_factory=list)
    touched: list[tuple] = field(default_factory=list)
    stored_record: SimpleNamespace | None = None

    def list_for_user(self, user_id: int):
        return list(self.credentials)

    def add(self, **kwargs):
        self.added_records.append(kwargs)
        record = SimpleNamespace(
            id=len(self.added_records),
            user=kwargs["user"],
            name=kwargs.get("name"),
            transports=list(kwargs.get("transports") or []),
            created_at=datetime.now(timezone.utc),
            last_used_at=None,
            backup_eligible=kwargs.get("backup_eligible", False),
            backup_state=kwargs.get("backup_state", False),
        )
        self.stored_record = record
        return record

    def find_by_credential_id(self, credential_id: str):
        if self.stored_record and getattr(self.stored_record, "credential_id", None) == credential_id:
            return self.stored_record
        return None

    def touch_usage(self, credential, new_sign_count: int):
        credential.sign_count = new_sign_count
        credential.last_used_at = datetime.now(timezone.utc)
        self.touched.append((credential, new_sign_count))


@pytest.fixture
def repository():
    return StubRepository()


@pytest.fixture
def service(repository):
    return PasskeyService(repository)


class DummyUser:
    def __init__(self, user_id: int, email: str, display_name: str | None = None):
        self.id = user_id
        self.email = email
        self.display_name = display_name or email


def test_generate_registration_options_excludes_existing_credentials(monkeypatch, service, repository):
    existing = StubCredential(credential_id=bytes_to_base64url(b"existing-cred"))
    repository.credentials.append(existing)

    captured: dict = {}

    class DummyOptions:
        def __init__(self):
            self.challenge = b"reg-challenge"

    def fake_generate_registration_options(**kwargs):
        captured.update(kwargs)
        return DummyOptions()

    monkeypatch.setattr(
        "shared.application.passkey_service.generate_registration_options",
        fake_generate_registration_options,
    )
    monkeypatch.setattr(
        "shared.application.passkey_service.options_to_json",
        lambda options: json.dumps({"challenge": "serialized"}),
    )

    user = DummyUser(1, "user@example.com", "User")
    options, challenge = service.generate_registration_options(user)

    assert challenge == bytes_to_base64url(b"reg-challenge")
    assert options == {"challenge": "serialized"}
    assert "exclude_credentials" in captured
    assert len(captured["exclude_credentials"]) == 1
    descriptor = captured["exclude_credentials"][0]
    assert descriptor.id == b"existing-cred"
    assert descriptor.type == "public-key"


def test_register_passkey_persists_repository(monkeypatch, service, repository):
    user = DummyUser(2, "person@example.com")

    class StubRegistrationCredential:
        @staticmethod
        def parse_raw(payload):
            return SimpleNamespace()

    monkeypatch.setattr(
        "shared.application.passkey_service.RegistrationCredential",
        StubRegistrationCredential,
    )

    verification = SimpleNamespace(
        credential_id=b"cred-id",
        credential_public_key=b"public-key",
        sign_count=10,
        fmt="packed",
        aaguid="0000",
        credential_device_type="multi-device",
        credential_backed_up=True,
    )

    monkeypatch.setattr(
        "shared.application.passkey_service.verify_registration_response",
        lambda **kwargs: verification,
    )

    record = service.register_passkey(
        user=user,
        payload=b"{}",
        expected_challenge="expected",
        transports=["internal"],
        name="Laptop",
    )

    assert repository.added_records, "repository.add should be invoked"
    added = repository.added_records[0]
    assert added["user"] is user
    assert added["credential_id"] == bytes_to_base64url(b"cred-id")
    assert added["public_key"] == bytes_to_base64url(b"public-key")
    assert added["sign_count"] == 10
    assert added["transports"] == ["internal"]
    assert added["name"] == "Laptop"
    assert added["attestation_format"] == "packed"
    assert added["aaguid"] == "0000"
    assert added["backup_eligible"] is True
    assert added["backup_state"] is True
    assert record.name == "Laptop"


def test_register_passkey_invalid_payload_raises_error(monkeypatch, service):
    class StubRegistrationCredential:
        @staticmethod
        def parse_raw(payload):
            raise ValueError("bad")

    monkeypatch.setattr(
        "shared.application.passkey_service.RegistrationCredential",
        StubRegistrationCredential,
    )

    with pytest.raises(PasskeyRegistrationError):
        service.register_passkey(
            user=DummyUser(3, "user@example.com"),
            payload=b"not-json",
            expected_challenge="challenge",
        )


def test_authenticate_updates_sign_count(monkeypatch, service, repository):
    stored_user = DummyUser(4, "login@example.com")
    stored_credential = SimpleNamespace(
        credential_id="cred-123",
        public_key=bytes_to_base64url(b"public"),
        sign_count=5,
        user=stored_user,
    )
    repository.stored_record = stored_credential

    credential_obj = SimpleNamespace(id="cred-123")

    class StubAuthenticationCredential:
        @staticmethod
        def parse_raw(payload):
            return credential_obj

    monkeypatch.setattr(
        "shared.application.passkey_service.AuthenticationCredential",
        StubAuthenticationCredential,
    )

    verification = SimpleNamespace(new_sign_count=42)
    monkeypatch.setattr(
        "shared.application.passkey_service.verify_authentication_response",
        lambda **kwargs: verification,
    )

    result_user = service.authenticate(payload=b"{}", expected_challenge="expected")

    assert result_user is stored_user
    assert repository.touched, "touch_usage should be called"
    touched_credential, new_sign_count = repository.touched[0]
    assert touched_credential.sign_count == 42
    assert new_sign_count == 42


def test_authenticate_invalid_payload_raises_error(monkeypatch, service):
    class StubAuthenticationCredential:
        @staticmethod
        def parse_raw(payload):
            raise ValueError("bad")

    monkeypatch.setattr(
        "shared.application.passkey_service.AuthenticationCredential",
        StubAuthenticationCredential,
    )

    with pytest.raises(PasskeyAuthenticationError):
        service.authenticate(payload=b"broken", expected_challenge="abc")
