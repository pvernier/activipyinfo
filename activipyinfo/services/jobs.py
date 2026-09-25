from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

import requests

from ..exceptions import error_from_response
from ..models.job import Job

if TYPE_CHECKING:
    from ..client import Client


def utc_offset_minutes() -> int:
    """The local time zone's offset from UTC, in minutes (used by exports)."""
    offset = datetime.now().astimezone().utcoffset()
    return int(offset.total_seconds() // 60) if offset else 0


class JobsService:
    """Background jobs and file staging, available as ``client.jobs``.

    Payloads follow the R package (``executeJob()``, ``stageImport()``).
    """

    def __init__(self, client: Client) -> None:
        self._client = client

    def start(
        self, job_type: str, descriptor: dict[str, Any], *, locale: str = "en"
    ) -> Job:
        """Start a job, e.g. ``start("exportForm", {...})``."""
        data = self._client.post(
            "jobs", {"type": job_type, "locale": locale, "descriptor": descriptor}
        )
        job = Job.from_api(data, self._client)
        job.type = job.type or job_type
        return job

    def get(self, job_id: str) -> Job:
        """Fetch a job's current state."""
        return Job.from_api(self._client.get(f"jobs/{job_id}"), self._client)

    def run(
        self,
        job_type: str,
        descriptor: dict[str, Any],
        *,
        timeout: float | None = None,
        poll_interval: float = 2.0,
        progress: Callable[[Job], None] | None = None,
    ) -> Job:
        """Start a job and wait until it completes (see :meth:`Job.wait`)."""
        return self.start(job_type, descriptor).wait(
            timeout=timeout, poll_interval=poll_interval, progress=progress
        )

    def download(self, job: Job, destination: Path) -> None:
        """Stream the result file of a completed job to ``destination``."""
        url = job.result.get("downloadUrl") or ""
        if not url.startswith(("http://", "https://")):
            if url.startswith("/"):
                url = f"{self._client.base_url}{url}"
            else:
                url = self._client.url(
                    f"jobs/{job.id}/{job.result['exportId']}/{job.result['filename']}"
                )
        response = self._client.request("GET", url, stream=True)
        with destination.open("wb") as file:
            for chunk in response.iter_content(chunk_size=1 << 16):
                file.write(chunk)

    def stage(
        self,
        content: str | bytes,
        *,
        direct: bool = False,
        content_type: str | None = None,
    ) -> str:
        """Upload a file for an import job and return its import id.

        Args:
            content: The file's text or bytes.
            direct: Upload straight to cloud storage (www.activityinfo.org
                only), as the R package does by default. The default uploads
                through ActivityInfo, which also works on self-managed servers.
            content_type: MIME type of the upload.
        """
        path = "imports/stage/direct" if direct else "imports/stage"
        staged = self._client.post(path)
        upload_url: str = staged["uploadUrl"]
        body = content.encode("utf-8") if isinstance(content, str) else content
        headers = {"Content-Type": content_type or "application/octet-stream"}

        if upload_url.startswith("/"):
            upload_url = f"{self._client.base_url}{upload_url}"
        if urlparse(upload_url).netloc == urlparse(self._client.base_url).netloc:
            self._client.request("PUT", upload_url, data=body, headers=headers)
        else:
            # A signed cloud storage URL: it must not receive our token.
            response = requests.put(
                upload_url, data=body, headers=headers, timeout=self._client.timeout
            )
            if not response.ok:
                raise error_from_response(response)
        import_id: str = staged["importId"]
        return import_id
