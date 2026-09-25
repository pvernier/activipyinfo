from __future__ import annotations

from typing import TYPE_CHECKING

from ..exceptions import ConfigurationError

if TYPE_CHECKING:
    from ..client import Client


class ClientBound:
    """Mixin for models that call the API through the client that created them."""

    _client: Client | None = None

    @property
    def client(self) -> Client:
        if self._client is None:
            raise ConfigurationError(
                f"{type(self).__name__} is not attached to a Client; "
                "pass client=... when creating it."
            )
        return self._client
