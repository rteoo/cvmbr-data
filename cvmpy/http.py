"""HTTP helpers with retries. Stream large ZIPs to disk; never hold them in RAM."""

from __future__ import annotations

import time
from pathlib import Path

import requests

from .constants import DOWNLOAD_TIMEOUT, HTTP_RETRIES, HTTP_TIMEOUT, REPO_URL, STREAM_CHUNK
from .exceptions import CVMPortalError


def user_agent() -> str:
    from . import __version__

    return f"cvmpy/{__version__} (+{REPO_URL})"


def enet_user_agent() -> str:
    from . import __version__

    return (
        "Mozilla/5.0 (compatible; cvmpy/{version}; +{repo})"
        .format(version=__version__, repo=REPO_URL)
    )


def _headers() -> dict[str, str]:
    return {"User-Agent": user_agent()}


def http_get(url: str, timeout: int = HTTP_TIMEOUT, retries: int = HTTP_RETRIES) -> bytes:
    last: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, headers=_headers(), timeout=timeout)
            response.raise_for_status()
            return response.content
        except (requests.RequestException, OSError) as exc:
            last = exc
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise CVMPortalError(f"GET {url} failed after {retries} attempts: {last}")


def http_stream_to(
    url: str,
    dest: Path,
    timeout: int = DOWNLOAD_TIMEOUT,
    retries: int = HTTP_RETRIES,
) -> None:
    """Download ``url`` to ``dest`` via a ``.part`` file, then replace.

    ceiling: autoindex size tokens are approximate; this function does not
    compare Content-Length against the catalog. Integrity is the catalog
    (modified, size_raw) stamp plus a non-empty payload.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    last: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(
                url, headers=_headers(), timeout=timeout, stream=True,
            )
            response.raise_for_status()
            wrote = 0
            try:
                with part.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=STREAM_CHUNK):
                        if chunk:
                            handle.write(chunk)
                            wrote += len(chunk)
            finally:
                response.close()
            if wrote == 0:
                raise CVMPortalError(f"empty payload for {url}")
            part.replace(dest)
            return
        except (requests.RequestException, OSError, CVMPortalError) as exc:
            last = exc
            if part.exists():
                part.unlink()
            if attempt < retries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise CVMPortalError(f"GET {url} failed after {retries} attempts: {last}")
