from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ._base import ClientBound
from .field import Field
from .ids import cuid
from .record import Record

if TYPE_CHECKING:
    from .client import Client


class Form(ClientBound):
    def __init__(
        self,
        label: str,
        fields: list | None = None,
        id: str | None = None,
        parentId: str | None = None,
        client: Client | None = None,
    ) -> None:
        self.id = cuid() if id is None else id
        self.label = label
        self.fields = fields if fields is not None else []
        self.records = None
        self.parentId = parentId
        self.databaseId: str | None = None
        self._client = client

    def __repr__(self):
        return f"Form({self.id}, {self.label}, {self.parentId})"

    def build_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "formResource": {
                "id": self.id,
                "parentId": self.parentId,
                "label": self.label,
                "type": "FORM",
                "visibility": "PRIVATE",
            },
            "formClass": {
                "id": self.id,
                "schemaVersion": 1,
                "databaseId": self.databaseId,
                "label": self.label,
                "elements": [],
            },
        }

        props_to_add = {
            "relevanceCondition": "",
            "validationCondition": "",
        }
        # This can maybe be moved to the Field class
        for field in self.fields:
            new_field = field.data.copy()
            new_field["id"] = field.id
            new_field.update(props_to_add)

            if "reference" in new_field:
                new_field["typeParameters"] = {
                    "cardinality": "single",
                    "range": [{"formId": new_field["reference"].id}],
                }
                new_field.pop("reference")
            else:
                new_field["typeParameters"] = {"barcode": False}

            if new_field["key"] is False:
                new_field.pop("key")

            payload["formClass"]["elements"].append(new_field)

        # FORM'S TEMPLATE
        # payload = {
        #     "formResource": {
        #         "id": uid1,
        #         "parentId": "qi350omk6tb6m3ry",
        #         "label": "Admin1",
        #         "type": "FORM",
        #         "visibility": "PRIVATE",
        #     },
        #     "formClass": {
        #         "id": uid1,
        #         "schemaVersion": 1,
        #         "databaseId": "cwfldm4lf9nc9n12",
        #         "label": "Admin1",
        #         "elements": [
        #             {
        #                 "id": uid2,
        #                 "code": "pcode",
        #                 "label": "P-code",
        #                 "description": "P-code of the admin1",
        #                 "relevanceCondition": "",
        #                 "validationCondition": "",
        #                 "required": True,
        #                 "type": "FREE_TEXT",
        #                 "key": True,
        #                 "typeParameters": {"barcode": False},
        #             },
        #             {
        #                 "id": uid3,
        #                 "code": "name",
        #                 "label": "Name",
        #                 "description": "Name of the admin1",
        #                 "relevanceCondition": "",
        #                 "validationCondition": "",
        #                 "required": True,
        #                 "type": "FREE_TEXT",
        #                 "typeParameters": {"barcode": False},
        #             },
        #         ],
        #     },
        # }
        return payload

    def get_fields(self) -> list:
        """Get the fields of the form in a list of Field objects"""

        schema = self.client.get(f"form/{self.id}/schema")

        self.fields = []
        elements = schema["elements"]
        for element in elements:
            field = Field(element, element["id"])
            self.fields.append(field)

        return self.fields

    def get_form_records(self, id) -> list:
        """Get the records of any form, not only for the instance
        This should maybe be moved somewhere else (utils?)"""
        return self.client.get(f"form/{id}/query")

    def add_record(self, record: Record) -> None:
        # Before adding the record, we need to replace the values of the reference
        # fields.
        # We need to replace the value with the id of the record in the reference form
        # which contains this values

        # XXX: There is no check or error handling here - TODO
        for i, f in enumerate(record.fields):
            if f.data["type"] == "reference":
                ref_form = f.data["reference"]

                # Get the records of the reference form
                # we need to do that here because we might have multiple reference
                # fields
                existing_records = self.get_form_records(ref_form.id)

                value_to_replace = record.values[i]

                # Replace the value with with the id of the reference record
                for er in existing_records:
                    # XXX: checking the name might not be robust enough.
                    # Can we know if a field is a key?
                    if value_to_replace in er.values():
                        record.values[i] = er["@id"]

        payload: dict[str, list] = {"changes": []}

        d = {}
        for i, v in enumerate(record.values):
            d[record.fields[i].id] = v

        change = {
            "formId": self.id,
            "recordId": record.id,
            "parentRecordId": None,
            "deleted": False,
            "fields": d,
        }
        payload["changes"].append(change)

        # RECORD'S TEMPLATE
        # payload = {
        #     "changes": [
        #         {
        #             "formId": "owwdl7bdye5ft99n",
        #             "recordId": uid5,
        #             "parentRecordId": None,
        #             "deleted": False,
        #             # "iz04yv98s6hjoj0i" is the uid of the field "pcode"
        #             # "cwrf280blfjw4x4j" is the uid of the field "name"
        #             "fields": {
        #                 "iz04yv98s6hjoj0i": "DEFs123456",
        #                 "cwrf280blfjw4x4j": "Tata",
        #             },
        #         }
        #     ]
        # }

        self.client.post("update", payload)

    # XXX: This does not work
    def update_record(self, record: Record, new_value: list) -> None:
        payload: dict[str, list] = {"changes": []}

        d = {}
        for i in range(len(record.values)):
            d[record.fields[i].id] = new_value[i]

        change = {
            "formId": self.id,
            "recordId": record.id,
            "parentRecordId": None,
            "deleted": False,
            "fields": d,
        }
        payload["changes"].append(change)

        # RECORD'S TEMPLATE
        # payload = {
        #     "changes": [
        #         {
        #             "formId": "owwdl7bdye5ft99n",
        #             "recordId": uid5,
        #             "parentRecordId": None,
        #             "deleted": False,
        #             # "iz04yv98s6hjoj0i" is the uid of the field "pcode"
        #             # "cwrf280blfjw4x4j" is the uid of the field "name"
        #             "fields": {
        #                 "iz04yv98s6hjoj0i": "DEFs123456",
        #                 "cwrf280blfjw4x4j": "Tata",
        #             },
        #         }
        #     ]
        # }

        self.client.post("update", payload)

    def delete_record(self, record: Record) -> None:
        payload: dict[str, list] = {"changes": []}

        change = {
            "formId": self.id,
            "recordId": record.id,
            "parentRecordId": None,
            "deleted": True,
            "fields": None,
        }
        payload["changes"].append(change)

        self.client.post("update", payload)
