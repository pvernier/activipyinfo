import requests

from .constant import Constant
from .field import Field
from .record import Record
from .utils import create_unique_id


class Form:
    def __init__(
        self, label, fields: list = None, id: str = None, parentId: str = None
    ) -> None:
        self.id = create_unique_id() if id is None else id
        self.label = label
        self.fields = fields if fields is not None else []
        self.records = None
        self.parentId = parentId
        self.token = Constant.token
        self.headers = Constant.headers
        self.base_url = Constant.base_url
        self.databaseId = None

    def __repr__(self):
        return f"Form({self.id}, {self.label}, {self.parentId})"

    def build_payload(self):
        payload = {
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

        r = requests.get(
            f"{self.base_url}/resources/form/{self.id}/schema",
            headers=self.headers,
        )

        elements = r.json()["elements"]
        for element in elements:
            field = Field(element, element["id"])
            self.fields.append(field)

        return self.fields

    def get_form_records(self, id) -> list:
        """Get the records of any form, not only for the instance
        This should maybe be moved somewhere else (utils?)"""
        r = requests.get(
            f"{self.base_url}/resources/form/{id}/query",
            headers=self.headers,
        )
        return r.json()

    def add_record(self, record: Record) -> None:
        # Before adding the record, we need to replace the values of the reference fields.
        # We need to replace the value with the id of the record in the reference form
        # which contains this values

        # XXX: There is no check or error handling here - TODO
        for i, f in enumerate(record.fields):
            if f.data["type"] == "reference":
                ref_form = f.data["reference"]

                # Get the records of the reference form
                # we need to do that here because we might have multiple reference fields
                existing_records = self.get_form_records(ref_form.id)

                value_to_replace = record.values[i]

                # Replace the value with with the id of the reference record
                for er in existing_records:
                    # XXX: checking the name might not be robust enough. Can we know if a field is a key?
                    if value_to_replace in er.values():
                        record.values[i] = er["@id"]

        payload = {"changes": []}

        d = {}
        for i, v in enumerate(record.values):
            d[record.fields[i].id] = v

        record = {
            "formId": self.id,
            "recordId": record.id,
            "parentRecordId": None,
            "deleted": False,
            "fields": d,
        }
        payload["changes"].append(record)

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
        #             "fields": {"iz04yv98s6hjoj0i": "DEFs123456", "cwrf280blfjw4x4j": "Tata"},
        #         }
        #     ]
        # }

        requests.post(
            f"{self.base_url}/resources/update",
            headers=self.headers,
            json=payload,
        )

    # XXX: This does not work
    def update_record(self, record: Record, new_value: list) -> None:
        payload = {"changes": []}

        d = {}
        for i, v in enumerate(record.values):
            d[record.fields[i].id] = new_value[i]

        record = {
            "formId": self.id,
            "recordId": record.id,
            "parentRecordId": None,
            "deleted": False,
            "fields": d,
        }
        payload["changes"].append(record)

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
        #             "fields": {"iz04yv98s6hjoj0i": "DEFs123456", "cwrf280blfjw4x4j": "Tata"},
        #         }
        #     ]
        # }

        requests.post(
            f"{self.base_url}/resources/update",
            headers=self.headers,
            json=payload,
        )

    def delete_record(self, record: Record) -> None:
        payload = {"changes": []}

        record = {
            "formId": self.id,
            "recordId": record.id,
            "parentRecordId": None,
            "deleted": True,
            "fields": None,
        }
        payload["changes"].append(record)

        requests.post(
            f"{self.base_url}/resources/update",
            headers=self.headers,
            json=payload,
        )
