import requests

from .constant import Constant
from .form import Form
from .utils import create_unique_id

# It seems that it's not possible to create folder within a folder using the API (it's possible from the web app) - to check


class Folder:
    def __init__(self, label: str, id: str = None, parentId: str = None) -> None:
        self.id = create_unique_id() if id is None else id
        self.label = label
        self.parentId = parentId
        self.type = "FOLDER"
        self.visibility = "PRIVATE"
        self.resourceDeletions = []
        self.lockUpdates = []
        self.lockDeletions = []
        self.roleUpdates = []
        self.roleDeletions = []
        self.languageUpdates = []
        self.languageDeletions = []
        self.originalLanguage = None
        self.continuousTranslation = None
        self.translationFromDbMemory = None
        self.thirdPartyTranslation = None
        self.publishedTemplate = None
        self.token = Constant.token
        self.headers = Constant.headers
        self.base_url = Constant.base_url
        self.databaseId = None

    def build_payload(self) -> dict:
        """"""

        ressource_updates = ["id", "parentId", "label", "type", "visibility"]
        attr_to_exclude = ["token", "headers", "base_url", "databaseId"]

        payload = {
            "resourceUpdates": [{}],
        }

        for attr in self.__dict__:
            if attr in ressource_updates and attr not in attr_to_exclude:
                payload["resourceUpdates"][0][attr] = self.__dict__[attr]
            elif attr not in attr_to_exclude:
                payload[attr] = self.__dict__[attr]

        # FOLDER'S TEMPLATE

        # payload = {
        #     "resourceUpdates": [
        #         {
        #             "id": uid,
        #             "parentId": self.id,
        #             "label": f"{name}",
        #             "type": "FOLDER",
        #             "visibility": "PRIVATE",
        #         }
        #     ],
        #     "resourceDeletions": [],
        #     "lockUpdates": [],
        #     "lockDeletions": [],
        #     "roleUpdates": [],
        #     "roleDeletions": [],
        #     "languageUpdates": [],
        #     "languageDeletions": [],
        #     "originalLanguage": None,
        #     "continuousTranslation": None,
        #     "translationFromDbMemory": None,
        #     "thirdPartyTranslation": None,
        #     "publishedTemplate": None,
        # }
        return payload

    def __repr__(self):
        return f"Folder({self.id}, {self.label}, {self.parentId})"

    def create_form(self, label: str, fields: dict) -> Form:
        """Create a form in the folder."""

        f = Form(label, fields)
        f.databaseId = self.databaseId
        f.parentId = self.id
        # print(f.fields)

        payload = f.build_payload()

        r = requests.post(
            f"{self.base_url}/resources/databases/{self.databaseId}/forms",
            headers=self.headers,
            json=payload,
        )
        # print(r.status_code)
        # print(r.json())

        return f
