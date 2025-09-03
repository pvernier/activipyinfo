from typing import Dict, List, Optional, Any

from .api_client import APIClient
from .config import Config
from .field import Field
from .record import Record
from .utils import create_unique_id


class Form:
    """Represents a form in an ActivityInfo database."""
    
    def __init__(
        self, 
        label: str, 
        fields: Optional[List[Field]] = None, 
        id: Optional[str] = None, 
        parentId: Optional[str] = None,
        api_client: Optional[APIClient] = None
    ) -> None:
        """Initialize a Form instance.
        
        Args:
            label: Form display name
            fields: List of Field objects
            id: Form identifier (generated if not provided)
            parentId: Parent folder identifier
            api_client: API client for making requests
        """
        self.id = create_unique_id() if id is None else id
        self.label = label
        self.fields = fields if fields is not None else []
        self.records: Optional[List] = None
        self.parentId = parentId
        self.api_client = api_client
        self.databaseId: Optional[str] = None

    def __repr__(self) -> str:
        return f"Form({self.id}, {self.label}, {self.parentId})"

    def _build_form_resource(self) -> Dict[str, Any]:
        """Build the form resource part of the payload."""
        return {
            "id": self.id,
            "parentId": self.parentId,
            "label": self.label,
            "type": Config.RESOURCE_TYPE_FORM,
            "visibility": Config.VISIBILITY_PRIVATE,
        }

    def _build_field_element(self, field: Field) -> Dict[str, Any]:
        """Build a single field element for the form schema.
        
        Args:
            field: Field instance to convert
            
        Returns:
            Dictionary representing the field element
        """
        element = field.data.copy()
        element["id"] = field.id
        element.update({
            "relevanceCondition": "",
            "validationCondition": "",
        })

        # Handle reference fields
        if "reference" in element:
            element["typeParameters"] = {
                "cardinality": "single",
                "range": [{"formId": element["reference"].id}],
            }
            element.pop("reference")
        else:
            element["typeParameters"] = {"barcode": False}

        # Remove key field if it's False
        if element.get("key") is False:
            element.pop("key")

        return element

    def _build_form_class(self) -> Dict[str, Any]:
        """Build the form class part of the payload."""
        elements = [self._build_field_element(field) for field in self.fields]
        
        return {
            "id": self.id,
            "schemaVersion": Config.FORM_SCHEMA_VERSION,
            "databaseId": self.databaseId,
            "label": self.label,
            "elements": elements,
        }

    def build_payload(self) -> Dict[str, Any]:
        """Build the complete API payload for form creation.
        
        Returns:
            Dictionary containing the form creation payload
        """
        return {
            "formResource": self._build_form_resource(),
            "formClass": self._build_form_class(),
        }

    def get_fields(self) -> List[Field]:
        """Get the fields of the form in a list of Field objects.
        
        Returns:
            List of Field objects representing the form schema
        """
        if not self.api_client:
            return []
            
        response_data = self.api_client.get(f"/resources/form/{self.id}/schema")
        
        elements = response_data["elements"]
        for element in elements:
            field = Field(element, element["id"])
            self.fields.append(field)

        return self.fields

    def get_form_records(self, form_id: str) -> Dict[str, Any]:
        """Get the records of any form.
        
        Args:
            form_id: Form identifier to get records for
            
        Returns:
            Dictionary containing form records
        """
        if not self.api_client:
            return {}
            
        return self.api_client.get(f"/resources/form/{form_id}/query")

    def _process_reference_fields(self, record: Record) -> None:
        """Process reference fields in a record before adding it.
        
        Args:
            record: Record instance to process
        """
        for i, field in enumerate(record.fields):
            if field.data["type"] == Config.FIELD_TYPE_REFERENCE:
                ref_form = field.data["reference"]
                existing_records = self.get_form_records(ref_form.id)
                value_to_replace = record.values[i]

                # Replace the value with the ID of the reference record
                for existing_record in existing_records:
                    if value_to_replace in existing_record.values():
                        record.values[i] = existing_record["@id"]
                        break

    def _build_record_payload(self, record: Record, deleted: bool = False) -> Dict[str, Any]:
        """Build the API payload for record operations.
        
        Args:
            record: Record instance
            deleted: Whether this is a delete operation
            
        Returns:
            Dictionary containing the record operation payload
        """
        fields_dict = {}
        if not deleted:
            for i, value in enumerate(record.values):
                fields_dict[record.fields[i].id] = value

        record_data = {
            "formId": self.id,
            "recordId": record.id,
            "parentRecordId": None,
            "deleted": deleted,
            "fields": fields_dict if not deleted else None,
        }

        return {"changes": [record_data]}

    def add_record(self, record: Record) -> None:
        """Add a record to the form.
        
        Args:
            record: Record instance to add
        """
        if not self.api_client:
            return
            
        # Process reference fields before adding
        self._process_reference_fields(record)
        
        payload = self._build_record_payload(record)
        self.api_client.post("/resources/update", payload)

    def update_record(self, record: Record, new_values: List[Any]) -> None:
        """Update an existing record with new values.
        
        Args:
            record: Record instance to update
            new_values: List of new values for the record
        """
        if not self.api_client:
            return
            
        # Create a copy of the record with new values
        updated_record = Record(record.fields, new_values)
        updated_record.id = record.id  # Keep the same ID
        
        payload = self._build_record_payload(updated_record)
        self.api_client.post("/resources/update", payload)

    def delete_record(self, record: Record) -> None:
        """Delete a record from the form.
        
        Args:
            record: Record instance to delete
        """
        if not self.api_client:
            return
            
        payload = self._build_record_payload(record, deleted=True)
        self.api_client.post("/resources/update", payload)
