import requests

from .constant import Constant
from .folder import Folder
from .form import Form


class Database:
    def __init__(self, id, label) -> None:
        self.id = id
        self.label = label
        self.token = Constant.token
        self.headers = Constant.headers
        self.base_url = Constant.base_url
        self.resources = {"folders": [], "forms": []}
        # TODO: add other attributes maybe in a metdata dict

    def __repr__(self):
        return f"Database('{self.id}')"

    def get_resources(self):
        """Get the resources of the database."""

        r = requests.get(
            f"{self.base_url}/resources/databases/{self.id}",
            headers=self.headers,
        )

        _res = r.json()["resources"]
        for element in _res:
            if element["type"] == "FOLDER":
                folder = Folder(element["label"], element["id"], element["parentId"])
                folder.databaseId = self.id
                self.resources["folders"].append(folder)
            elif element["type"] == "FORM":
                form = Form(element["label"], None, element["id"], element["parentId"])
                form.databaseId = self.id
                self.resources["forms"].append(form)
        return self.resources

    def create_folder(self, name: str) -> Folder:
        """Create a folder in the database."""

        f = Folder(name)
        f.databaseId = self.id
        f.parentId = self.id
        payload = f.build_payload()

        r = requests.post(
            f"{self.base_url}/resources/databases/{self.id}",
            headers=self.headers,
            json=payload,
        )
        # print(r.status_code)
        # print(r.json())

        return f
