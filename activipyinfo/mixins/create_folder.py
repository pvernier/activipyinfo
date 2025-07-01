import requests

# from ..folder import Folder


class CreateFolderMixin:
    # def create_folder(self, id):
    #     print(f"create folder from {self.__class__.__name__} with token {self.token}")
    #     return Folder(id)

    def create_folder(self, name: str):
        """Create a folder in the database."""

        print("**** IM HERE *****")
        print(self.__class__.__name__)
        print(super(CreateFolderMixin, self))
        print("**** IM HERE *****")
        # f = Folder(name, self.id)
        # payload = f.build_payload()

        # r = requests.post(
        #     f"{self.base_url}/resources/databases/{self.id}",
        #     headers=self.headers,
        #     json=payload,
        # )
        # print(r.status_code)
        # print(r.json())

        # return f
