"""Live checks of roles and users. They create and delete a scratch database.

The user test sends a real invitation email, so it also needs
ACTIVITYINFO_TEST_EMAIL (an address you control).
"""

import os

import pytest

from activipyinfo import (
    Grant,
    Operation,
    Role,
    RoleParameter,
    database_permissions,
    resource_permissions,
)

pytestmark = pytest.mark.integration


def test_role_round_trip(scratch_database):
    db = scratch_database
    folder = db.add_folder("Partners")
    role = Role(
        "Reporting partner",
        grants=[
            Grant(db, resource_permissions()),
            Grant(
                folder,
                resource_permissions(
                    add_record=True, edit_record="ISBLANK(@user.partner) == FALSE"
                ),
                optional=True,
            ),
        ],
        permissions=database_permissions(manage_users=True),
        parameters=[RoleParameter("partner", "Partner", folder.id)],
    )

    db.roles.add(role)

    # Checks what the server keeps of the R-style payload (permission
    # objects with formulas, optional grants).
    saved = db.refresh().roles.get(role.id)
    assert saved.label == "Reporting partner"
    folder_grant = saved.grant_for(folder)
    assert folder_grant.optional is True
    edit = next(p for p in folder_grant.permissions if p.operation == "EDIT_RECORD")
    assert edit.filter == "ISBLANK(@user.partner) == FALSE"
    assert Operation.MANAGE_USERS in [p.operation for p in saved.permissions]

    saved.label = "Partner"
    assert db.roles.update(saved).label == "Partner"

    db.roles.delete(saved)
    assert role.id not in [r.id for r in db.refresh().roles]


def test_user_lifecycle(scratch_database):
    email = os.environ.get("ACTIVITYINFO_TEST_EMAIL")
    if not email:
        pytest.skip("set ACTIVITYINFO_TEST_EMAIL to test inviting a user")
    db = scratch_database
    folder = db.add_folder("Field")
    viewer = db.roles.add(Role("Viewer", grants=[Grant(folder, optional=True)]))

    user = db.users.add(email, "activipyinfo test", viewer, resources=[folder])
    assert user.role.role_id == viewer.id

    fetched = db.users.get(email)
    assert fetched.user_id == user.user_id
    assert folder.id in fetched.role.resources

    db.users.set_role(fetched, viewer, resources=[db])
    assert db.id in db.users.get(user.user_id).role.resources

    db.users.remove(user)
    assert email.lower() not in [u.email.lower() for u in db.users.list()]
