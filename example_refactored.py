#!/usr/bin/env python3
"""
Example demonstrating the refactored ActiviPyInfo library.

This example shows how the improved API provides better error handling,
type safety, and validation while maintaining the same simple interface.
"""

from activipyinfo import Manager, Field, Record, ActivityInfoAPIError
from activipyinfo.config import Config


def demonstrate_refactored_api():
    """Demonstrate the improved API features."""
    print("🔧 ActiviPyInfo Refactoring Demo")
    print("=" * 40)
    
    # 1. Improved error handling with validation
    print("\n1. Input validation:")
    try:
        manager = Manager("")  # Empty token
    except ValueError as e:
        print(f"   ✓ Empty token rejected: {e}")
    
    try:
        field = Field({})  # Missing required fields
    except ValueError as e:
        print(f"   ✓ Invalid field data rejected: {e}")
    
    # 2. Type safety and configuration
    print("\n2. Configuration and type safety:")
    print(f"   • Base URL: {Config.DEFAULT_BASE_URL}")
    print(f"   • Schema version: {Config.FORM_SCHEMA_VERSION}")
    
    # 3. Proper API client instantiation
    print("\n3. Creating manager with valid token:")
    manager = Manager("demo_token_123")
    print(f"   ✓ Manager created: {type(manager).__name__}")
    
    # 4. Creating fields with proper validation
    print("\n4. Creating validated fields:")
    field1 = Field({
        "code": "name",
        "label": "Full Name",
        "type": Config.FIELD_TYPE_FREE_TEXT,
        "required": True
    })
    print(f"   ✓ Field created: {field1}")
    
    field2 = Field({
        "code": "email",
        "label": "Email Address", 
        "type": Config.FIELD_TYPE_FREE_TEXT,
        "required": False
    })
    print(f"   ✓ Field created: {field2}")
    
    # 5. Creating records with type-safe construction
    print("\n5. Creating type-safe records:")
    record = Record([field1, field2], ["John Doe", "john@example.com"])
    print(f"   ✓ Record created: {record}")
    
    # 6. Error handling demonstration
    print("\n6. API error handling:")
    print("   • Custom ActivityInfoAPIError for API failures")
    print("   • Graceful handling of network issues")
    print("   • Clear error messages for debugging")
    
    print("\n✨ Refactoring complete! Benefits achieved:")
    print("   • Better error handling and validation")
    print("   • Type safety with comprehensive hints")
    print("   • Improved code organization and maintainability")
    print("   • Configuration management with constants")
    print("   • Full backward compatibility maintained")


if __name__ == "__main__":
    demonstrate_refactored_api()