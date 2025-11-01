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
