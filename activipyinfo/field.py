from typing import Dict, Optional

from .utils import create_unique_id


class Field:
    """Represents a field in an ActivityInfo form."""
    
    def __init__(self, data: Dict, id: Optional[str] = None) -> None:
        """Initialize a Field instance.
        
        Args:
            data: Dictionary containing field configuration
            id: Field identifier (generated if not provided)
        """
        self.id = create_unique_id() if id is None else id
        self.data = data

    def __repr__(self) -> str:
        return f"Field({self.id})"
