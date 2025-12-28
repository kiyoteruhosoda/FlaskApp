import pytest

from webapp.extensions import db
from core.models.group import Group, GroupHierarchyError


@pytest.fixture
def session(app_context):
    with app_context.app_context():
        yield db.session
        db.session.rollback()


def test_assign_parent_prevents_cycle(session):
    root = Group(name="Root")
    child = Group(name="Child")
    session.add_all([root, child])
    session.commit()

    child.assign_parent(root)
    session.commit()

    with pytest.raises(GroupHierarchyError):
        root.assign_parent(child)


def test_assign_parent_rejects_self(session):
    group = Group(name="Solo")
    session.add(group)
    session.commit()

    with pytest.raises(GroupHierarchyError):
        group.assign_parent(group)


def test_iter_descendants_includes_nested_children(session):
    root = Group(name="Root")
    child_a = Group(name="Child A")
    child_b = Group(name="Child B")
    grandchild = Group(name="Grandchild")

    child_a.assign_parent(root)
    child_b.assign_parent(root)
    grandchild.assign_parent(child_a)

    session.add_all([root, child_a, child_b, grandchild])
    session.commit()

    descendants = list(root.iter_descendants())
    descendant_names = {group.name for group in descendants}

    assert descendant_names == {"Child A", "Child B", "Grandchild"}
    assert all(isinstance(group, Group) for group in descendants)
