"""HTTP helpers with retries. Stream large ZIPs to disk; never hold them in RAM."""

from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from pathlib import Path

import requests

from .constants import (
    CIRCUIT_FAILURES,
    DOWNLOAD_TIMEOUT,
    HTTP_RETRIES,
    HTTP_TIMEOUT,
    MAX_RETRY_DELAY,
    REPO_URL,
    STREAM_CHUNK,
)
from .exceptions import CVMPortalError

RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})


def user_agent() -> str:
    from . import __version__

    return f"cvmbr-data/{__version__} (+{REPO_URL})"


def enet_user_agent() -> str:
    from . import __version__

    return (
        "Mozilla/5.0 (compatible; cvmbr-data/{version}; +{repo})"
        .format(version=__version__, repo=REPO_URL)
    )


def _headers() -> dict[str, str]:
    return {"User-Agent": user_agent()}


def header_map(headers) -> dict[str, str]:
    if not headers:
        return {}
    return {str(key).lower(): str(value) for key, value in headers.items()}


def retry_delay(attempt: int, headers: dict[str, str] | None = None) -> float:
    """Seconds to wait before the next attempt. Honors Retry-After when present."""
    headers = headers or {}
    raw = headers.get("retry-after")
    if raw:
        try:
            return min(float(raw), MAX_RETRY_DELAY)
        except ValueError:
            try:
                when = parsedate_to_datetime(raw)
                seconds = when.timestamp() - time.time()
                return min(max(seconds, 0.0), MAX_RETRY_DELAY)
            except (TypeError, ValueError, OverflowError):
                pass
    base = 1.5 * (2 ** attempt)
    jitter = random.uniform(0.0, 0.5 * base)
    return min(base + jitter, MAX_RETRY_DELAY)


@dataclass(frozen=True)
class HttpResult:
    content: bytes
    status_code: int
    headers: dict[str, str]
    url: str
    not_modified: bool = False


@dataclass(frozen=True)
class StreamResult:
    path: Path
    status_code: int
    headers: dict[str, str]
    byte_size: int
    not_modified: bool = False


class HttpClient:
    """Portal GET with finite backoff, 429/503 handling, and a simple circuit."""

    def __init__(
        self,
        *,
        retries: int = HTTP_RETRIES,
        circuit_failures: int = CIRCUIT_FAILURES,
        sleep=time.sleep,
    ):
        self.retries = retries
        self.circuit_failures = circuit_failures
        self._sleep = sleep
        self._failures = 0
        self._open = False
        self._lock = threading.Lock()

    def _raise_if_open(self, url: str) -> None:
        with self._lock:
            if self._open:
                raise CVMPortalError(
                    f"circuit open after {self.circuit_failures} repeated failures; skipped {url}"
                )

    def _note_success(self) -> None:
        with self._lock:
            self._failures = 0

    def _note_failure(self) -> None:
        with self._lock:
            self._failures += 1
            if self._failures >= self.circuit_failures:
                self._open = True

    def _open_response(
        self,
        url: str,
        *,
        timeout: int,
        etag: str | None,
        last_modified: str | None,
        stream: bool,
    ) -> requests.Response:
        headers = _headers()
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        return requests.get(url, headers=headers, timeout=timeout, stream=stream)

    def _retryable(self, status: int) -> bool:
        return status in RETRYABLE_STATUS

    def fetch_bytes(
        self,
        url: str,
        *,
        timeout: int = HTTP_TIMEOUT,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> HttpResult:
        self._raise_if_open(url)
        last: Exception | None = None
        last_headers: dict[str, str] = {}
        for attempt in range(self.retries):
            response = None
            try:
                response = self._open_response(
                    url,
                    timeout=timeout,
                    etag=etag,
                    last_modified=last_modified,
                    stream=False,
                )
                last_headers = header_map(response.headers)
                if response.status_code == 304:
                    self._note_success()
                    return HttpResult(
                        content=b"",
                        status_code=304,
                        headers=last_headers,
                        url=url,
                        not_modified=True,
                    )
                if self._retryable(response.status_code):
                    last = CVMPortalError(f"GET {url} returned {response.status_code}")
                    if attempt < self.retries - 1:
                        self._sleep(retry_delay(attempt, last_headers))
                        continue
                    self._note_failure()
                    raise CVMPortalError(
                        f"GET {url} failed after {self.retries} attempts: {last}"
                    )
                if response.status_code >= 400:
                    raise CVMPortalError(f"GET {url} returned {response.status_code}")
                content = response.content
                self._note_success()
                return HttpResult(
                    content=content,
                    status_code=response.status_code,
                    headers=last_headers,
                    url=url,
                )
            except CVMPortalError:
                raise
            except (requests.RequestException, OSError) as exc:
                last = exc
                if attempt < self.retries - 1:
                    self._sleep(retry_delay(attempt, last_headers))
                    continue
                self._note_failure()
                raise CVMPortalError(
                    f"GET {url} failed after {self.retries} attempts: {last}"
                ) from last
            finally:
                if response is not None:
                    response.close()
        raise CVMPortalError(f"GET {url} failed after {self.retries} attempts: {last}")

    def stream_to(
        self,
        url: str,
        dest: Path,
        *,
        timeout: int = DOWNLOAD_TIMEOUT,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> StreamResult:
        """Download ``url`` to ``dest`` via a ``.part`` file, then replace.

        A 304 leaves ``dest`` untouched. Partial ``.part`` files are deleted.
        """
        dest.parent.mkdir(parents=True, exist_ok=True)
        part = dest.with_suffix(dest.suffix + ".part")
        last: Exception | None = None
        last_headers: dict[str, str] = {}
        for attempt in range(self.retries):
            self._raise_if_open(url)
            response = None
            try:
                response = self._open_response(
                    url,
                    timeout=timeout,
                    etag=etag,
                    last_modified=last_modified,
                    stream=True,
                )
                last_headers = header_map(response.headers)
                if response.status_code == 304:
                    response.close()
                    response = None
                    self._note_success()
                    size = dest.stat().st_size if dest.exists() else 0
                    return StreamResult(
                        path=dest,
                        status_code=304,
                        headers=last_headers,
                        byte_size=size,
                        not_modified=True,
                    )
                if self._retryable(response.status_code):
                    last = CVMPortalError(f"GET {url} returned {response.status_code}")
                    response.close()
                    response = None
                    if part.exists():
                        part.unlink()
                    if attempt < self.retries - 1:
                        self._sleep(retry_delay(attempt, last_headers))
                        continue
                    self._note_failure()
                    raise CVMPortalError(
                        f"GET {url} failed after {self.retries} attempts: {last}"
                    )
                if response.status_code >= 400:
                    response.close()
                    response = None
                    raise CVMPortalError(f"GET {url} returned {response.status_code}")
                wrote = 0
                with part.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=STREAM_CHUNK):
                        if chunk:
                            handle.write(chunk)
                            wrote += len(chunk)
                response.close()
                response = None
                if wrote == 0:
                    if part.exists():
                        part.unlink()
                    raise CVMPortalError(f"empty payload for {url}")
                part.replace(dest)
                self._note_success()
                return StreamResult(
                    path=dest,
                    status_code=200,
                    headers=last_headers,
                    byte_size=wrote,
                )
            except CVMPortalError:
                if part.exists():
                    part.unlink()
                raise
            except (requests.RequestException, OSError) as exc:
                last = exc
                if part.exists():
                    part.unlink()
                if attempt < self.retries - 1:
                    self._sleep(retry_delay(attempt, last_headers))
                    continue
                self._note_failure()
                raise CVMPortalError(
                    f"GET {url} failed after {self.retries} attempts: {last}"
                ) from last
            finally:
                if response is not None:
                    response.close()
        raise CVMPortalError(f"GET {url} failed after {self.retries} attempts: {last}")


def http_get(
    url: str,
    timeout: int = HTTP_TIMEOUT,
    retries: int = HTTP_RETRIES,
) -> bytes:
    result = HttpClient(retries=retries).fetch_bytes(url, timeout=timeout)
    return result.content


def http_stream_to(
    url: str,
    dest: Path,
    timeout: int = DOWNLOAD_TIMEOUT,
    retries: int = HTTP_RETRIES,
) -> None:
    HttpClient(retries=retries).stream_to(url, dest, timeout=timeout)
