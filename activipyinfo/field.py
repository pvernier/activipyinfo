from typing import Dict, Optional

from .utils import create_unique_id


class Field:
    """Represents a field in an ActivityInfo form."""
    
    def __init__(self, data: Dict, id: Optional[str] = None) -> None:
        """Initialize a Field instance.
        
        Args:
            data: Dictionary containing field configuration
            id: Field identifier (generated if not provided)
            
        Raises:
            ValueError: If data is None or missing required keys
        """
        if not data or not isinstance(data, dict):
            raise ValueError("Field data must be a non-empty dictionary")
        
        required_keys = ['type', 'label']
        missing_keys = [key for key in required_keys if key not in data]
        if missing_keys:
            raise ValueError(f"Field data missing required keys: {missing_keys}")
            
        self.id = create_unique_id() if id is None else id
        self.data = data

    def __repr__(self) -> str:
        return f"Field({self.id})"
