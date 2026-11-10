"""Local mirror of portal ZIPs. Re-download only when the catalog stamp moves."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from .artifacts import SourceObjectMeta, build_source_meta, sha256_file
from .constants import PARSER_VERSION
from .exceptions import CVMPortalError
from .http import HttpClient


def _stamp_path(dest: Path) -> Path:
    return dest.with_suffix(dest.suffix + ".meta")


def _catalog_key(file_entry: dict) -> dict[str, str]:
    return {"modified": file_entry["modified"], "size_raw": file_entry["size_raw"]}


def _read_stamp(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _write_stamp(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload), encoding="utf-8")


def _validate_archive(dest: Path) -> None:
    if dest.suffix.lower() != ".zip":
        return
    if not zipfile.is_zipfile(dest):
        dest.unlink(missing_ok=True)
        raise CVMPortalError(f"corrupt ZIP at {dest}")


def _parse_fetched_at(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class Mirror:
    """Local copy of the portal's ZIPs, keyed by the path under /dados/."""

    def __init__(self, root: Path, client: HttpClient | None = None):
        self.root = root
        self.client = client or HttpClient()
        self.downloaded = 0
        self.cached = 0

    def path_for(self, url: str) -> Path:
        return self.root / url.split("/dados/", 1)[1]

    def get(self, file_entry: dict) -> Path:
        return Path(self.describe(file_entry).local_path)

    def describe(self, file_entry: dict) -> SourceObjectMeta:
        dest = self.path_for(file_entry["url"])
        stamp_path = _stamp_path(dest)
        want = _catalog_key(file_entry)
        existing = _read_stamp(stamp_path) if stamp_path.exists() else {}
        if (
            dest.exists()
            and existing.get("modified") == want["modified"]
            and existing.get("size_raw") == want["size_raw"]
        ):
            self.cached += 1
            return self._meta_from_disk(
                dest, file_entry, existing, cached=True, status_code=200,
            )

        result = self.client.stream_to(
            file_entry["url"],
            dest,
            etag=existing.get("etag"),
            last_modified=existing.get("last_modified"),
        )
        if result.not_modified:
            if not dest.exists() or dest.stat().st_size == 0:
                raise CVMPortalError(f"empty payload for {file_entry['url']}")
            self.cached += 1
            payload = self._stamp_payload(
                dest,
                file_entry,
                headers=result.headers,
                status_code=304,
                existing=existing,
            )
            _write_stamp(stamp_path, payload)
            return self._meta_from_disk(
                dest, file_entry, payload, cached=True, status_code=304,
            )

        if not dest.exists() or dest.stat().st_size == 0:
            raise CVMPortalError(f"empty payload for {file_entry['url']}")
        _validate_archive(dest)
        payload = self._stamp_payload(
            dest,
            file_entry,
            headers=result.headers,
            status_code=result.status_code,
            existing={},
        )
        _write_stamp(stamp_path, payload)
        self.downloaded += 1
        return self._meta_from_disk(
            dest, file_entry, payload, cached=False, status_code=result.status_code,
        )

    def _stamp_payload(
        self,
        dest: Path,
        file_entry: dict,
        *,
        headers: dict[str, str],
        status_code: int,
        existing: dict,
    ) -> dict:
        from . import __version__

        digest = existing.get("sha256") or sha256_file(dest)
        fetched = existing.get("fetched_at") or datetime.now(timezone.utc).isoformat(timespec="seconds")
        return {
            "modified": file_entry["modified"],
            "size_raw": file_entry["size_raw"],
            "sha256": digest,
            "byte_size": dest.stat().st_size,
            "fetched_at": fetched,
            "etag": headers.get("etag") or existing.get("etag"),
            "last_modified": headers.get("last-modified") or existing.get("last_modified"),
            "http_headers": headers,
            "status_code": status_code,
            "library_version": __version__,
            "parser_version": PARSER_VERSION,
        }

    def _meta_from_disk(
        self,
        dest: Path,
        file_entry: dict,
        stamp: dict,
        *,
        cached: bool,
        status_code: int,
    ) -> SourceObjectMeta:
        digest = stamp.get("sha256")
        if not digest:
            digest = sha256_file(dest)
            stamp = {**stamp, "sha256": digest, "byte_size": dest.stat().st_size}
            _write_stamp(_stamp_path(dest), {**_catalog_key(file_entry), **stamp})
        return build_source_meta(
            dest,
            source_url=file_entry["url"],
            catalog_modified=file_entry["modified"],
            catalog_size_raw=file_entry["size_raw"],
            fetched_at=_parse_fetched_at(stamp.get("fetched_at")),
            http_headers=stamp.get("http_headers") or {},
            library_version=stamp.get("library_version"),
            parser_version=stamp.get("parser_version") or PARSER_VERSION,
            status_code=int(stamp.get("status_code") or status_code),
            cached=cached,
            sha256=digest,
        )
