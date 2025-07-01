import requests

from .constant import Constant
from .database import Database


class Manager:
    def __init__(self, token: str) -> None:
        Constant.token = token
        Constant.headers = {
            "Authorization": f"Bearer {token}",
            "content-type": "application/json",
        }

        self.token = token
        self.headers = Constant.headers
        self.base_url = Constant.base_url

    def get_dbs(self) -> list:
        """"""
        dbs = []

        url = f"{self.base_url}/resources/databases"
        response = requests.get(url, headers=self.headers)

        for r in response.json():
            db = Database(r["databaseId"], r["label"])
            dbs.append(db)

        return dbs

    def get_db(self, db_id: str) -> Database:
        dbs = self.get_dbs()
        for db in dbs:
            if db.id == db_id:
                return db
