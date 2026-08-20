"""Warehouse-facing source-object descriptors. Public; does not import Strateo Markets."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from .constants import PARSER_VERSION


@dataclass(frozen=True)
class SourceObjectMeta:
    """Checksummed raw artifact for warehouse registration."""

    sha256: str
    byte_size: int
    source_url: str
    local_path: str
    fetched_at: datetime
    http_headers: dict[str, str]
    library_version: str
    parser_version: str
    catalog_modified: str
    catalog_size_raw: str
    status_code: int = 200
    cached: bool = False


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_source_meta(
    path: Path,
    *,
    source_url: str,
    catalog_modified: str,
    catalog_size_raw: str,
    fetched_at: datetime | None = None,
    http_headers: dict[str, str] | None = None,
    library_version: str | None = None,
    parser_version: str = PARSER_VERSION,
    status_code: int = 200,
    cached: bool = False,
    sha256: str | None = None,
) -> SourceObjectMeta:
    from . import __version__

    payload_sha = sha256 if sha256 is not None else sha256_file(path)
    return SourceObjectMeta(
        sha256=payload_sha,
        byte_size=path.stat().st_size,
        source_url=source_url,
        local_path=str(path),
        fetched_at=fetched_at or datetime.now(UTC),
        http_headers=http_headers or {},
        library_version=library_version or __version__,
        parser_version=parser_version,
        catalog_modified=catalog_modified,
        catalog_size_raw=catalog_size_raw,
        status_code=status_code,
        cached=cached,
    )
