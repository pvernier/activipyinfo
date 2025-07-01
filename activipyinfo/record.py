from .utils import create_unique_id


class Record:
    def __init__(self, fields, values) -> None:
        self.id = create_unique_id()
        self.fields = fields
        self.values = values

    def __repr__(self):
        return f"Record({self.id})"
