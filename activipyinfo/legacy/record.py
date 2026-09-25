from ..ids import cuid


class Record:
    def __init__(self, fields, values) -> None:
        self.id = cuid()
        self.fields = fields
        self.values = values

    def __repr__(self):
        return f"Record({self.id})"
