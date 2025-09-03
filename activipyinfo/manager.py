from typing import List, Optional

from .api_client import APIClient
from .database import Database


class Manager:
    """Main manager class for ActivityInfo API interactions."""
    
    def __init__(self, token: str) -> None:
        """Initialize the Manager with an API token.
        
        Args:
            token: ActivityInfo API authentication token
            
        Raises:
            ValueError: If token is empty or None
        """
        if not token or not isinstance(token, str):
            raise ValueError("Token must be a non-empty string")
        self.api_client = APIClient(token)

    def get_dbs(self) -> List[Database]:
        """Get all databases accessible with the current token.
        
        Returns:
            List of Database objects
        """
        response_data = self.api_client.get("/resources/databases")
        
        databases = []
        for db_data in response_data:
            db = Database(
                db_data["databaseId"], 
                db_data["label"], 
                api_client=self.api_client
            )
            databases.append(db)
        
        return databases

    def get_db(self, db_id: str) -> Optional[Database]:
        """Get a specific database by ID.
        
        Args:
            db_id: Database identifier
            
        Returns:
            Database object if found, None otherwise
            
        Raises:
            ValueError: If db_id is empty or None
        """
        if not db_id or not isinstance(db_id, str):
            raise ValueError("Database ID must be a non-empty string")
            
        databases = self.get_dbs()
        for db in databases:
            if db.id == db_id:
                return db
        return None
