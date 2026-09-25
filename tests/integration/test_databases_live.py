"""Live checks of folders. They run in a scratch folder (see conftest.py).

PowerShell:
    $env:ACTIVITYINFO_TOKEN = "..."
    $env:ACTIVITYINFO_ALLOW_WRITES = "1"
    $env:ACTIVITYINFO_TEST_DATABASE = "<database id>"
    uv run pytest -m integration
"""

import pytest

from activipyinfo import Folder, NoMatchError

pytestmark = pytest.mark.integration


def test_folder_lifecycle(sandbox):
    db, root = sandbox.db, sandbox.folder
    assert isinstance(root, Folder)
    assert db.refresh().folder(root.id).label == root.label

    # Open question in the plan: can folders be nested through the API?
    a = root.add_folder("A")
    b = root.add_folder("B")
    assert db.refresh().resource(a.id).parent_id == root.id

    a.rename("A renamed")
    assert db.refresh().resource(a.id).label == "A renamed"

    a.move(b)
    assert db.refresh().resource(a.id).parent_id == b.id

    a.delete()
    with pytest.raises(NoMatchError):
        db.refresh().resource(a.id)
