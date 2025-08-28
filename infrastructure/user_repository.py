from typing import List
from core.models.user import User as UserModel, Role
from domain.user.entities import User
from domain.user.repository import UserRepository


class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session):
        self.session = session

    def get_by_email(self, email: str) -> User | None:
        model = UserModel.query.filter_by(email=email).first()
        if model:
            return self._to_domain(model)
        return None

    def add(self, user: User, role_names: List[str]) -> User:
        model = UserModel(email=user.email, password_hash=user.password_hash, totp_secret=user.totp_secret)
        if role_names:
            roles = Role.query.filter(Role.name.in_(role_names)).all()
            if len(roles) != len(role_names):
                raise ValueError("Role not found")
            model.roles.extend(roles)
        self.session.add(model)
        self.session.commit()
        user.id = model.id
        return user

    def get_model(self, user: User) -> UserModel:
        return UserModel.query.get(user.id)

    def _to_domain(self, model: UserModel) -> User:
        user = User(email=model.email, totp_secret=model.totp_secret, id=model.id, created_at=model.created_at)
        user.password_hash = model.password_hash
        return user
