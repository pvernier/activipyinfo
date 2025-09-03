from typing import List, Any

from .utils import create_unique_id


class Record:
    """Represents a data record in an ActivityInfo form."""
    
    def __init__(self, fields: List, values: List[Any]) -> None:
        """Initialize a Record instance.
        
        Args:
            fields: List of Field objects
            values: List of values corresponding to the fields
        """
        self.id = create_unique_id()
        self.fields = fields
        self.values = values

    def __repr__(self) -> str:
        return f"Record({self.id})"
