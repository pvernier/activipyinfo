from typing import Dict, List, Optional

from .api_client import APIClient
from .form import Form
from .utils import create_unique_id


class Folder:
    """Represents a folder in an ActivityInfo database."""
    
    def __init__(
        self, 
        label: str, 
        id: Optional[str] = None, 
        parentId: Optional[str] = None,
        api_client: Optional[APIClient] = None
    ) -> None:
        """Initialize a Folder instance.
        
        Args:
            label: Folder display name
            id: Folder identifier (generated if not provided)
            parentId: Parent folder/database identifier
            api_client: API client for making requests
        """
        self.id = create_unique_id() if id is None else id
        self.label = label
        self.parentId = parentId
        self.type = "FOLDER"
        self.visibility = "PRIVATE"
        self.resourceDeletions: List = []
        self.lockUpdates: List = []
        self.lockDeletions: List = []
        self.roleUpdates: List = []
        self.roleDeletions: List = []
        self.languageUpdates: List = []
        self.languageDeletions: List = []
        self.originalLanguage: Optional[str] = None
        self.continuousTranslation: Optional[bool] = None
        self.translationFromDbMemory: Optional[bool] = None
        self.thirdPartyTranslation: Optional[bool] = None
        self.publishedTemplate: Optional[str] = None
        self.api_client = api_client
        self.databaseId: Optional[str] = None

    def build_payload(self) -> Dict:
        """Build the API payload for folder creation.
        
        Returns:
            Dictionary containing the folder creation payload
        """
        resource_updates = ["id", "parentId", "label", "type", "visibility"]
        attr_to_exclude = ["api_client", "databaseId"]

        payload = {
            "resourceUpdates": [{}],
        }

        for attr in self.__dict__:
            if attr in resource_updates and attr not in attr_to_exclude:
                payload["resourceUpdates"][0][attr] = self.__dict__[attr]
            elif attr not in attr_to_exclude:
                payload[attr] = self.__dict__[attr]

        return payload

    def __repr__(self) -> str:
        return f"Folder({self.id}, {self.label}, {self.parentId})"

    def create_form(self, label: str, fields: List) -> Form:
        """Create a form in the folder.
        
        Args:
            label: Form display name
            fields: List of Field objects for the form
            
        Returns:
            Created Form instance
        """
        form = Form(label, fields, api_client=self.api_client)
        form.databaseId = self.databaseId
        form.parentId = self.id

        payload = form.build_payload()

        if self.api_client and self.databaseId:
            self.api_client.post(f"/resources/databases/{self.databaseId}/forms", payload)

        return form
