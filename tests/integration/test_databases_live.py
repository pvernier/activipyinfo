"""Write tests against the live API. They create and delete a database.

Run with: ACTIVITYINFO_TOKEN=... ACTIVITYINFO_ALLOW_WRITES=1 \
          uv run pytest -m integration
"""

import pytest

from activipyinfo import Folder, NoMatchError

pytestmark = pytest.mark.integration


def test_folder_lifecycle(scratch_database):
    db = scratch_database

    folder = db.add_folder("Admin boundaries")
    assert isinstance(folder, Folder)
    assert db.refresh().folder("Admin boundaries").id == folder.id

    # Open question in the plan: can folders be nested through the API?
    sub = folder.add_folder("Archive")
    assert db.refresh().resource(sub.id).parent_id == folder.id

    sub.rename("Old data")
    assert db.refresh().resource(sub.id).label == "Old data"

    sub.move(db)
    assert db.refresh().resource(sub.id).parent_id == db.id

    sub.delete()
    with pytest.raises(NoMatchError):
        db.refresh().resource(sub.id)


def test_billing_account(scratch_database):
    assert scratch_database.billing_account().id == scratch_database.billing_account_id
