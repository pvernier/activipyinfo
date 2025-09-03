"""Configuration constants for ActiviPyInfo."""

class Config:
    """Configuration constants for ActivityInfo API."""
    
    # API Configuration
    DEFAULT_BASE_URL = "https://www.activityinfo.org"
    
    # Resource Types
    RESOURCE_TYPE_FOLDER = "FOLDER"
    RESOURCE_TYPE_FORM = "FORM"
    
    # Field Types
    FIELD_TYPE_FREE_TEXT = "FREE_TEXT"
    FIELD_TYPE_REFERENCE = "reference"
    
    # Visibility Options
    VISIBILITY_PRIVATE = "PRIVATE"
    VISIBILITY_PUBLIC = "PUBLIC"
    
    # Schema Version
    FORM_SCHEMA_VERSION = 1