from typing import Dict, List, Optional

from .api_client import APIClient
from .config import Config
from .folder import Folder
from .form import Form


class Database:
    """Represents an ActivityInfo database."""
    
    def __init__(self, id: str, label: str, api_client: APIClient) -> None:
        """Initialize a Database instance.
        
        Args:
            id: Database identifier
            label: Database display name
            api_client: API client for making requests
        """
        self.id = id
        self.label = label
        self.api_client = api_client
        self.resources: Dict[str, List] = {"folders": [], "forms": []}

    def __repr__(self) -> str:
        return f"Database('{self.id}')"

    def get_resources(self) -> Dict[str, List]:
        """Get the resources of the database.
        
        Returns:
            Dictionary containing folders and forms lists
        """
        response_data = self.api_client.get(f"/resources/databases/{self.id}")
        
        resources = response_data["resources"]
        for element in resources:
            if element["type"] == Config.RESOURCE_TYPE_FOLDER:
                folder = Folder(
                    element["label"], 
                    element["id"], 
                    element["parentId"],
                    api_client=self.api_client
                )
                folder.databaseId = self.id
                self.resources["folders"].append(folder)
            elif element["type"] == Config.RESOURCE_TYPE_FORM:
                form = Form(
                    element["label"], 
                    None, 
                    element["id"], 
                    element["parentId"],
                    api_client=self.api_client
                )
                form.databaseId = self.id
                self.resources["forms"].append(form)
        return self.resources

    def create_folder(self, name: str) -> Folder:
        """Create a folder in the database.
        
        Args:
            name: Name for the new folder
            
        Returns:
            Created Folder instance
            
        Raises:
            ValueError: If name is empty or None
        """
        if not name or not isinstance(name, str):
            raise ValueError("Folder name must be a non-empty string")
            
        folder = Folder(name, api_client=self.api_client)
        folder.databaseId = self.id
        folder.parentId = self.id
        payload = folder.build_payload()

        self.api_client.post(f"/resources/databases/{self.id}", payload)
        
        return folder
