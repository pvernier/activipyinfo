import pytest

from activipyinfo import (
    Folder,
    Form,
    Grant,
    Operation,
    Permission,
    Role,
    RoleAssignment,
    RoleParameter,
    database_permissions,
    resource_permissions,
)
from activipyinfo.ids import is_cuid

# ----------------------------------------------------------------------
# Permissions
# ----------------------------------------------------------------------


def test_resource_permissions_default_to_view_only():
    assert resource_permissions() == [Permission(Operation.VIEW)]


def test_resource_permissions_with_formula_and_flags():
    permissions = resource_permissions(
        add_record=True, edit_record="[partner] == @user.partner", discover=True
    )

    assert permissions == [
        Permission(Operation.VIEW),
        Permission(Operation.ADD_RECORD),
        Permission(Operation.EDIT_RECORD, filter="[partner] == @user.partner"),
        Permission(Operation.DISCOVER),
    ]


def test_resource_permissions_can_drop_view():
    assert resource_permissions(view=False, audit=True) == [Permission(Operation.AUDIT)]


def test_reviewer_only_marks_add_and_edit_record():
    permissions = resource_permissions(
        add_record=True, edit_record=True, delete_record=True, reviewer_only=True
    )

    categories = {str(p.operation): p.security_categories for p in permissions}
    assert categories == {
        "VIEW": (),
        "ADD_RECORD": ("reviewer",),
        "EDIT_RECORD": ("reviewer",),
        "DELETE_RECORD": (),
    }


def test_resource_permissions_reject_other_types():
    with pytest.raises(TypeError, match="add_record"):
        resource_permissions(add_record=1)


def test_database_permissions():
    assert database_permissions() == []
    assert database_permissions(manage_users=True, manage_roles=True) == [
        Permission(Operation.MANAGE_USERS),
        Permission(Operation.MANAGE_ROLES),
    ]


def test_permission_serialization_matches_r_package():
    assert Permission(Operation.VIEW).to_api() == {
        "operation": "VIEW",
        "securityCategories": [],
    }
    assert Permission(
        Operation.EDIT_RECORD, filter="x == 1", security_categories=("reviewer",)
    ).to_api() == {
        "operation": "EDIT_RECORD",
        "filter": "x == 1",
        "securityCategories": ["reviewer"],
    }


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        ("VIEW", Permission(Operation.VIEW)),
        (
            {"operation": "EDIT_RECORD", "filter": "f", "securityCategories": ["r"]},
            Permission(Operation.EDIT_RECORD, filter="f", security_categories=("r",)),
        ),
        ({"operation": "VIEW", "filter": ""}, Permission(Operation.VIEW)),
    ],
)
def test_permission_parsing_accepts_strings_and_objects(data, expected):
    assert Permission.from_api(data) == expected


def test_unknown_operation_is_kept_as_string():
    permission = Permission.from_api("TIME_TRAVEL")

    assert permission.operation == "TIME_TRAVEL"
    assert permission.to_api()["operation"] == "TIME_TRAVEL"


# ----------------------------------------------------------------------
# Grants and parameters
# ----------------------------------------------------------------------


def test_grant_accepts_resource_objects():
    grant = Grant(Folder("f1", "Folder", "FOLDER"))

    assert grant.resource_id == "f1"
    assert grant.operations == [Operation.VIEW]


def test_grant_serialization():
    grant = Grant("f1", resource_permissions(add_record=True), optional=True)

    assert grant.to_api() == {
        "resourceId": "f1",
        "operations": [
            {"operation": "VIEW", "securityCategories": []},
            {"operation": "ADD_RECORD", "securityCategories": []},
        ],
        "optional": True,
    }
    assert Grant.from_api(grant.to_api()) == grant


def test_grant_parsing_with_string_operations():
    grant = Grant.from_api({"resourceId": "db1", "operations": ["VIEW", "AUDIT"]})

    assert grant.operations == [Operation.VIEW, Operation.AUDIT]
    assert grant.optional is False


def test_role_parameter():
    parameter = RoleParameter("partner", "Partner", Form("fp", "Partners", "FORM"))

    assert parameter.to_api() == {
        "parameterId": "partner",
        "label": "Partner",
        "range": "fp",
    }


@pytest.mark.parametrize("bad_id", ["1partner", "has space", "", "x" * 33])
def test_role_parameter_rejects_invalid_ids(bad_id):
    with pytest.raises(ValueError, match="parameter id"):
        RoleParameter(bad_id, "Label", "range")


# ----------------------------------------------------------------------
# Roles
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Data entry", "dataentry"),
        ("Équipe 2 (terrain)", "equipe2terrain"),
        ("2024 Viewers", "viewers"),
        ("A" * 40, "a" * 32),
    ],
)
def test_role_id_is_derived_from_label(label, expected):
    assert Role(label).id == expected


def test_role_id_falls_back_to_cuid():
    assert is_cuid(Role("مدخل البيانات").id)


@pytest.mark.parametrize("bad_id", ["Admin", "1admin", "data-entry", "a" * 33])
def test_role_rejects_invalid_ids(bad_id):
    with pytest.raises(ValueError, match="role id"):
        Role("Admin", id=bad_id)


def test_role_serialization_matches_r_package():
    role = Role(
        "Reporting partner",
        id="rp",
        grants=[Grant("db1", resource_permissions(add_record=True))],
        permissions=database_permissions(manage_users=True),
        parameters=[RoleParameter("partner", "Partner", "fp")],
    )

    assert role.to_api() == {
        "id": "rp",
        "label": "Reporting partner",
        "permissions": [{"operation": "MANAGE_USERS", "securityCategories": []}],
        "parameters": [{"parameterId": "partner", "label": "Partner", "range": "fp"}],
        "filters": [],
        "grants": [
            {
                "resourceId": "db1",
                "operations": [
                    {"operation": "VIEW", "securityCategories": []},
                    {"operation": "ADD_RECORD", "securityCategories": []},
                ],
                "optional": False,
            }
        ],
        "grantBased": True,
    }


def test_role_round_trip():
    role = Role(
        "Viewer",
        grants=[Grant("f1", optional=True)],
        parameters=[RoleParameter("region", "Region", "fr")],
    )

    parsed = Role.from_api(role.to_api())

    assert parsed.to_api() == role.to_api()
    assert parsed.raw == role.to_api()


def test_grant_for():
    grant = Grant("f1")
    role = Role("Viewer", grants=[grant])

    assert role.grant_for("f1") is grant
    assert role.grant_for(Folder("f1", "F", "FOLDER")) is grant
    assert role.grant_for("f2") is None


# ----------------------------------------------------------------------
# Role assignments
# ----------------------------------------------------------------------


def test_role_assignment_serialization():
    assignment = RoleAssignment(
        Role("Viewer"), {"partner": "rec1"}, [Folder("f1", "F", "FOLDER"), "db1"]
    )

    assert assignment.to_api() == {
        "id": "viewer",
        "parameters": {"partner": "rec1"},
        "resources": ["f1", "db1"],
    }


@pytest.mark.parametrize(
    "data",
    [
        {"id": "rp", "parameters": {"partner": "r1"}, "resources": ["db1"]},
        {"roleId": "rp", "roleParameters": {"partner": "r1"}, "roleResources": ["db1"]},
    ],
)
def test_role_assignment_parsing_accepts_both_key_styles(data):
    assert RoleAssignment.from_api(data) == RoleAssignment(
        "rp", {"partner": "r1"}, ["db1"]
    )
