from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ..exceptions import ConfigurationError, JobFailedError, JobTimeoutError

if TYPE_CHECKING:
    from ..client import Client

__all__ = ["Job"]


@dataclass(eq=False)
class Job:
    """A server-side job (import, export, duplication...).

    Jobs run in the background: :meth:`wait` polls until the job completes
    and :meth:`download` saves the file an export job produced.
    """

    id: str
    type: str | None = None
    state: str = "STARTED"
    percent_complete: float = 0.0
    result: dict[str, Any] = field(default_factory=dict)
    error_code: str | None = None
    error_message: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)
    _client: Client | None = field(default=None, init=False, repr=False)

    @classmethod
    def from_api(cls, data: dict[str, Any], client: Client | None = None) -> Job:
        error = data.get("error") or {}
        descriptor = data.get("descriptor") or {}
        job = cls(
            id=data["id"],
            type=data.get("type") or descriptor.get("type"),
            state=str(data.get("state") or "STARTED").upper(),
            percent_complete=float(data.get("percentComplete") or 0.0),
            # The reference names it jobResult or result, depending on the page.
            result=dict(data.get("jobResult") or data.get("result") or {}),
            error_code=error.get("code"),
            error_message=error.get("localizedMessage") or error.get("message"),
            raw=data,
        )
        job._client = client
        return job

    def __repr__(self) -> str:
        return f"Job(id={self.id!r}, type={self.type!r}, state={self.state!r})"

    @property
    def client(self) -> Client:
        if self._client is None:
            raise ConfigurationError(f"{self!r} is not attached to a Client.")
        return self._client

    @property
    def completed(self) -> bool:
        return self.state == "COMPLETED"

    @property
    def failed(self) -> bool:
        return self.state == "FAILED"

    def refresh(self) -> Job:
        """Fetch the job's current state."""
        latest = self.client.jobs.get(self.id)
        self.state = latest.state
        self.percent_complete = latest.percent_complete
        self.result = latest.result
        self.error_code = latest.error_code
        self.error_message = latest.error_message
        self.raw = latest.raw
        self.type = self.type or latest.type
        return self

    def wait(
        self,
        *,
        timeout: float | None = None,
        poll_interval: float = 2.0,
        progress: Callable[[Job], None] | None = None,
    ) -> Job:
        """Poll until the job completes and return it.

        Args:
            timeout: Give up after this many seconds (``JobTimeoutError``);
                the job keeps running on the server.
            poll_interval: Seconds between two status requests.
            progress: Called with the job after each status request, e.g.
                ``progress=lambda job: print(job.percent_complete)``.

        Raises:
            JobFailedError: the job failed on the server.
        """
        clock = time.monotonic
        deadline = None if timeout is None else clock() + timeout
        sleep = getattr(self.client, "_sleep", time.sleep)
        while True:
            if progress is not None:
                progress(self)
            if self.completed:
                return self
            if self.failed or self.state not in ("STARTED", "PENDING", "RUNNING"):
                raise JobFailedError(self)
            if deadline is not None and clock() >= deadline:
                raise JobTimeoutError(
                    f"{self!r} did not complete within {timeout} seconds "
                    f"({self.percent_complete:.0f}% done)"
                )
            sleep(poll_interval)
            self.refresh()

    def download(self, destination: str | Path | None = None) -> Path:
        """Save the file produced by an export job and return its path.

        ``destination`` is a file path, or a directory in which the server's
        file name is used (default: the current directory).
        """
        if not self.completed:
            raise ValueError(f"{self!r} has not completed: call wait() first")
        filename = self.result.get("filename")
        if not filename:
            raise ValueError(f"{self!r} did not produce a file")
        target = Path(destination) if destination is not None else Path.cwd()
        if target.is_dir():
            target = target / filename
        self.client.jobs.download(self, target)
        return target
