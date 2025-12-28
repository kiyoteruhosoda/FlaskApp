from __future__ import annotations

from typing import TYPE_CHECKING, Iterator

from sqlalchemy import UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.db import db

if TYPE_CHECKING:  # pragma: no cover
    from core.models.user import User


BigInt = db.BigInteger().with_variant(db.Integer, "sqlite")


group_user_membership = db.Table(
    "group_user_membership",
    db.Column("group_id", BigInt, db.ForeignKey("user_group.id"), primary_key=True),
    db.Column("user_id", BigInt, db.ForeignKey("user.id"), primary_key=True),
    db.UniqueConstraint("group_id", "user_id", name="uq_group_user_membership"),
)


class GroupHierarchyError(ValueError):
    """Raised when an invalid group hierarchy is detected."""


class Group(db.Model):
    __tablename__ = "user_group"
    __table_args__ = (UniqueConstraint("name", name="uq_user_group_name"),)

    id: Mapped[int] = mapped_column(BigInt, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(db.String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(db.Text, nullable=True)
    parent_id: Mapped[int | None] = mapped_column(
        BigInt, db.ForeignKey("user_group.id"), nullable=True
    )

    parent: Mapped["Group | None"] = relationship(
        "Group",
        remote_side="Group.id",
        back_populates="children",
    )
    children: Mapped[list["Group"]] = relationship(
        "Group",
        back_populates="parent",
    )
    users: Mapped[list["User"]] = relationship(
        "User",
        secondary=group_user_membership,
        back_populates="groups",
    )

    def ensure_assignable_parent(self, candidate: Group | None) -> None:
        """Validate that *candidate* can become this group's parent.

        The hierarchy must remain acyclic and a group cannot become its own parent.
        """

        if candidate is None:
            return

        target_id = self.id
        ancestor: Group | None = candidate
        while ancestor is not None:
            if ancestor is self:
                raise GroupHierarchyError("Group cannot be its own parent.")
            if target_id is not None and ancestor.id == target_id:
                raise GroupHierarchyError("Group hierarchy would become cyclic.")
            ancestor = ancestor.parent

    def assign_parent(self, parent: Group | None) -> None:
        """Assign a parent group after validating the hierarchy."""

        self.ensure_assignable_parent(parent)
        self.parent = parent

    def iter_descendants(self) -> Iterator[Group]:
        """Iterate over all descendant groups."""

        stack: list[Group] = list(self.children)
        seen_ids: set[int] = set()
        while stack:
            current = stack.pop()
            if current.id is not None and current.id in seen_ids:
                continue
            if current.id is not None:
                seen_ids.add(current.id)
            yield current
            stack.extend(current.children)

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return f"Group(id={self.id!r}, name={self.name!r})"
