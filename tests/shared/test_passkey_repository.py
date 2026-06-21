"""Tests for the SQLAlchemy passkey repository implementation."""
from __future__ import annotations

from core.db import db
from core.models.user import User
from shared.infrastructure.passkey_repository import SqlAlchemyPasskeyRepository


def test_delete_allows_re_registering_same_credential(app_context):
    """Deleting a passkey should allow registering the same credential again."""

    with app_context.app_context():
        user = User(email="passkey-user@example.com", username="passkey-user")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

        repository = SqlAlchemyPasskeyRepository(db.session)

        record = repository.add(
            user=user,
            credential_id="test-credential-id",
            public_key="test-public-key",
            sign_count=1,
            transports=["internal"],
            name="Laptop",
            attestation_format="packed",
            aaguid="test-aaguid",
            backup_eligible=True,
            backup_state=False,
        )

        repository.delete(record)

        recreated = repository.add(
            user=user,
            credential_id="test-credential-id",
            public_key="test-public-key",
            sign_count=1,
            transports=["internal"],
            name="Laptop",
            attestation_format="packed",
            aaguid="test-aaguid",
            backup_eligible=True,
            backup_state=False,
        )

        assert recreated.id is not None
        assert recreated.credential_id == "test-credential-id"

        rows = repository.list_for_user(user.id)
        assert len(rows) == 1
        assert rows[0].id == recreated.id


def test_update_existing_overwrites_metadata(app_context):
    """Updating an existing credential should persist new metadata values."""

    with app_context.app_context():
        user = User(email="update-user@example.com", username="update-user")
        user.set_password("secret")
        db.session.add(user)
        db.session.commit()

        repository = SqlAlchemyPasskeyRepository(db.session)

        record = repository.add(
            user=user,
            credential_id="initial-id",
            public_key="initial-key",
            sign_count=1,
            transports=["internal"],
            name="Initial",
            attestation_format="packed",
            aaguid="initial-aaguid",
            backup_eligible=False,
            backup_state=False,
        )

        updated = repository.update_existing(
            record,
            public_key="updated-key",
            sign_count=5,
            transports=["internal", "hybrid"],
            name="Updated",
            attestation_format="packed",
            aaguid="updated-aaguid",
            backup_eligible=True,
            backup_state=True,
        )

        assert updated.id == record.id
        assert updated.public_key == "updated-key"
        assert updated.sign_count == 5
        assert updated.transports == ["internal", "hybrid"]
        assert updated.name == "Updated"
        assert updated.aaguid == "updated-aaguid"
        assert updated.backup_eligible is True
        assert updated.backup_state is True
