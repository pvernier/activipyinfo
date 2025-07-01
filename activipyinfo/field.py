from .utils import create_unique_id


class Field:
    def __init__(self, data: dict, id: str = None) -> None:
        self.id = create_unique_id() if id is None else id
        self.data = data

    def __repr__(self):
        return f"Field({self.id})"
