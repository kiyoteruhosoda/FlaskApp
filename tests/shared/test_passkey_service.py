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
from webauthn.helpers.structs import (
    AuthenticationCredential,
    AuthenticatorAssertionResponse,
    AuthenticatorAttestationResponse,
    RegistrationCredential,
)


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

    verification = SimpleNamespace(
        credential_id=b"cred-id",
        credential_public_key=b"public-key",
        sign_count=10,
        fmt="packed",
        aaguid="0000",
        credential_device_type="multi-device",
        credential_backed_up=True,
    )

    captured: dict = {}

    def fake_verify_registration_response(**kwargs):
        captured.update(kwargs)
        return verification

    monkeypatch.setattr(
        "shared.application.passkey_service.verify_registration_response",
        fake_verify_registration_response,
    )

    raw_id_bytes = b"cred-id"
    client_data_bytes = b"client-data"
    attestation_bytes = b"attestation"
    payload_dict = {
        "id": bytes_to_base64url(raw_id_bytes),
        "rawId": bytes_to_base64url(raw_id_bytes),
        "response": {
            "attestationObject": bytes_to_base64url(attestation_bytes),
            "clientDataJSON": bytes_to_base64url(client_data_bytes),
        },
        "type": "public-key",
    }

    record = service.register_passkey(
        user=user,
        payload=json.dumps(payload_dict).encode("utf-8"),
        expected_challenge=bytes_to_base64url(b"expected"),
        transports=["internal"],
        name="Laptop",
    )

    credential = captured["credential"]
    assert isinstance(credential, RegistrationCredential)
    assert credential.id == payload_dict["id"]
    assert credential.raw_id == raw_id_bytes
    assert isinstance(credential.response, AuthenticatorAttestationResponse)
    assert credential.response.client_data_json == client_data_bytes
    assert credential.response.attestation_object == attestation_bytes
    assert captured["expected_challenge"] == b"expected"
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
    with pytest.raises(PasskeyRegistrationError):
        service.register_passkey(
            user=DummyUser(3, "user@example.com"),
            payload=b"\xff",
            expected_challenge=bytes_to_base64url(b"challenge"),
        )


def test_authenticate_updates_sign_count(monkeypatch, service, repository):
    stored_user = DummyUser(4, "login@example.com")
    credential_id_bytes = b"cred-123"
    stored_credential = SimpleNamespace(
        credential_id=bytes_to_base64url(credential_id_bytes),
        public_key=bytes_to_base64url(b"public"),
        sign_count=5,
        user=stored_user,
    )
    repository.stored_record = stored_credential

    verification = SimpleNamespace(new_sign_count=42)
    captured: dict = {}

    def fake_verify_authentication_response(**kwargs):
        captured.update(kwargs)
        return verification

    monkeypatch.setattr(
        "shared.application.passkey_service.verify_authentication_response",
        fake_verify_authentication_response,
    )

    authenticator_data_bytes = b"data"
    client_data_bytes = b"client"
    signature_bytes = b"sig"
    payload_dict = {
        "id": bytes_to_base64url(credential_id_bytes),
        "rawId": bytes_to_base64url(credential_id_bytes),
        "response": {
            "authenticatorData": bytes_to_base64url(authenticator_data_bytes),
            "clientDataJSON": bytes_to_base64url(client_data_bytes),
            "signature": bytes_to_base64url(signature_bytes),
        },
        "type": "public-key",
    }

    result_user = service.authenticate(
        payload=json.dumps(payload_dict).encode("utf-8"),
        expected_challenge=bytes_to_base64url(b"expected"),
    )

    assert result_user is stored_user
    credential = captured["credential"]
    assert isinstance(credential, AuthenticationCredential)
    assert credential.id == payload_dict["id"]
    assert credential.raw_id == credential_id_bytes
    assert isinstance(credential.response, AuthenticatorAssertionResponse)
    assert credential.response.client_data_json == client_data_bytes
    assert credential.response.authenticator_data == authenticator_data_bytes
    assert credential.response.signature == signature_bytes
    assert captured["expected_challenge"] == b"expected"
    assert repository.touched, "touch_usage should be called"
    touched_credential, new_sign_count = repository.touched[0]
    assert touched_credential.sign_count == 42
    assert new_sign_count == 42


def test_authenticate_invalid_payload_raises_error(monkeypatch, service):
    with pytest.raises(PasskeyAuthenticationError):
        service.authenticate(
            payload=b"\xff",
            expected_challenge=bytes_to_base64url(b"challenge"),
        )


def test_register_passkey_invalid_challenge(monkeypatch, service):
    user = DummyUser(5, "register@example.com")
    raw_id_bytes = b"cred-id"
    payload_dict = {
        "id": bytes_to_base64url(raw_id_bytes),
        "rawId": bytes_to_base64url(raw_id_bytes),
        "response": {
            "attestationObject": bytes_to_base64url(b"attestation"),
            "clientDataJSON": bytes_to_base64url(b"client-data"),
        },
        "type": "public-key",
    }

    with pytest.raises(PasskeyRegistrationError) as exc:
        service.register_passkey(
            user=user,
            payload=json.dumps(payload_dict).encode("utf-8"),
            expected_challenge=None,
        )

    assert exc.value.args[0] == "invalid_challenge"


def test_authenticate_invalid_challenge(monkeypatch, service, repository):
    repository.stored_record = SimpleNamespace(
        credential_id=bytes_to_base64url(b"cred-456"),
        public_key=bytes_to_base64url(b"public"),
        sign_count=0,
        user=DummyUser(6, "auth@example.com"),
    )

    credential_bytes = b"cred-456"
    payload_dict = {
        "id": bytes_to_base64url(credential_bytes),
        "rawId": bytes_to_base64url(credential_bytes),
        "response": {
            "authenticatorData": bytes_to_base64url(b"data"),
            "clientDataJSON": bytes_to_base64url(b"client"),
            "signature": bytes_to_base64url(b"sig"),
        },
        "type": "public-key",
    }

    with pytest.raises(PasskeyAuthenticationError) as exc:
        service.authenticate(
            payload=json.dumps(payload_dict).encode("utf-8"),
            expected_challenge=None,
        )

    assert exc.value.args[0] == "invalid_challenge"
