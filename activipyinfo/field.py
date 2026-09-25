from .ids import cuid


class Field:
    def __init__(self, data: dict, id: str | None = None) -> None:
        self.id = cuid() if id is None else id
        self.data = data

    def __repr__(self):
        return f"Field({self.id})"
