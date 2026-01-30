import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from shared.application.auth_service import AuthService
from shared.domain.user import UserRegistrationService
from core.db import db
from core.models.user import Role, User as UserModel
from shared.infrastructure.user_repository import SqlAlchemyUserRepository


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", future=True)
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    session = SessionLocal()
    db.Model.metadata.create_all(engine)
    try:
        yield session
    finally:
        session.close()
        db.Model.metadata.drop_all(engine)


@pytest.fixture
def auth_service(session):
    repo = SqlAlchemyUserRepository(session)
    registrar = UserRegistrationService(repo)
    return AuthService(repo, registrar)


def _create_role(session, name: str = "guest") -> Role:
    role = Role(name=name)
    session.add(role)
    session.commit()
    return role


def test_register_and_authenticate_with_custom_session(session, auth_service):
    _create_role(session)

    user = auth_service.register("user@example.com", "secret", roles=["guest"])

    assert user.id is not None
    assert user.is_active

    stmt = select(UserModel).filter_by(id=user.id)
    persisted_user = session.execute(stmt).scalar_one()
    assert persisted_user.email == "user@example.com"
    assert persisted_user.roles and persisted_user.roles[0].name == "guest"

    authenticated = auth_service.authenticate("user@example.com", "secret")
    assert authenticated is not None
    assert isinstance(authenticated, UserModel)
    assert authenticated.id == user.id

    assert auth_service.authenticate("user@example.com", "wrong") is None


def test_totp_registration_flow_uses_repository_session(session, auth_service):
    _create_role(session, "guest_totp")

    pending_user = auth_service.register_with_pending_totp(
        "totp@example.com", "secret", roles=["guest_totp"]
    )
    assert pending_user.id is not None
    assert pending_user.is_active is False

    stmt = select(UserModel).filter_by(id=pending_user.id)
    persisted_user = session.execute(stmt).scalar_one()
    assert not persisted_user.is_active

    activated_user = auth_service.activate_user_with_totp(pending_user, "TOTPSECRET")
    assert activated_user.is_active

    session.refresh(persisted_user)
    assert persisted_user.is_active
    assert persisted_user.totp_secret == "TOTPSECRET"


def test_inactive_user_replaced_on_register(session, auth_service):
    _create_role(session, "guest_replace")

    pending_user = auth_service.register_with_pending_totp(
        "replace@example.com", "old-secret", roles=["guest_replace"]
    )
    assert pending_user.id is not None

    new_user = auth_service.register(
        "replace@example.com", "new-secret", roles=["guest_replace"]
    )
    assert new_user.id is not None

    stmt = select(UserModel).filter_by(email="replace@example.com")
    persisted_users = session.execute(stmt).scalars().all()
    assert len(persisted_users) == 1
    persisted_user = persisted_users[0]
    assert persisted_user.is_active
    assert persisted_user.check_password("new-secret")
    assert not persisted_user.check_password("old-secret")

    authenticated = auth_service.authenticate("replace@example.com", "new-secret")
    assert authenticated is not None
    assert isinstance(authenticated, UserModel)
    assert authenticated.id == new_user.id
    assert auth_service.authenticate("replace@example.com", "old-secret") is None
