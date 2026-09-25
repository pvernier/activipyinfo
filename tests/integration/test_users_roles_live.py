"""Live checks of roles and users, in a scratch folder (see conftest.py).

Roles are database-wide, so each test deletes the role it creates. They need
the MANAGE_ROLES permission, and are skipped without it. The user test sends
a real invitation email, so it also needs ACTIVITYINFO_TEST_EMAIL.
"""

import os

import pytest

from activipyinfo import (
    Grant,
    Operation,
    PermissionDeniedError,
    Role,
    RoleParameter,
    TextField,
    cuid,
    database_permissions,
    resource_permissions,
)

pytestmark = pytest.mark.integration


def add_role_or_skip(db, role):
    try:
        return db.roles.add(role)
    except PermissionDeniedError:
        pytest.skip("the token's user cannot manage roles in this database")


def test_role_round_trip(sandbox):
    db, folder = sandbox.db, sandbox.folder
    partners = folder.add_form("Partners", [TextField("Name", code="name", key=True)])
    role = Role(
        "activipyinfo test partner",
        id=f"aitest{cuid()[:10]}",
        grants=[
            Grant(folder, resource_permissions()),
            Grant(
                partners,
                resource_permissions(
                    add_record=True, edit_record="ISBLANK(@user.partner) == FALSE"
                ),
                optional=True,
            ),
        ],
        permissions=database_permissions(manage_users=True),
        parameters=[RoleParameter("partner", "Partner", partners)],
    )

    add_role_or_skip(db, role)
    try:
        # What the server kept of the R-style payload (permission objects
        # with formulas, optional grants).
        saved = db.refresh().roles.get(role.id)
        assert saved.label == role.label
        grant = saved.grant_for(partners)
        assert grant.optional is True
        edit = next(p for p in grant.permissions if p.operation == "EDIT_RECORD")
        assert edit.filter == "ISBLANK(@user.partner) == FALSE"
        assert Operation.MANAGE_USERS in [p.operation for p in saved.permissions]

        saved.label = "activipyinfo test partner (renamed)"
        assert db.roles.update(saved).label == saved.label
    finally:
        db.roles.delete(role.id)
    assert role.id not in [r.id for r in db.refresh().roles]


def test_user_lifecycle(sandbox):
    email = os.environ.get("ACTIVITYINFO_TEST_EMAIL")
    if not email:
        pytest.skip("set ACTIVITYINFO_TEST_EMAIL to test inviting a user")
    db, folder = sandbox.db, sandbox.folder
    viewer = add_role_or_skip(
        db,
        Role(
            "activipyinfo test viewer",
            id=f"aitest{cuid()[:10]}",
            grants=[Grant(folder, optional=True)],
        ),
    )
    try:
        user = db.users.add(email, "activipyinfo test", viewer, resources=[folder])
        try:
            assert user.role.role_id == viewer.id
            fetched = db.users.get(email)
            assert fetched.user_id == user.user_id
            assert folder.id in fetched.role.resources
        finally:
            db.users.remove(user)
        assert email.lower() not in [u.email.lower() for u in db.users.list()]
    finally:
        db.roles.delete(viewer.id)
