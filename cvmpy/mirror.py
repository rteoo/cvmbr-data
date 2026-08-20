"""Local mirror of portal ZIPs. Re-download only when the catalog stamp moves."""

from __future__ import annotations

import json
from pathlib import Path

from .exceptions import CVMPortalError
from .http import http_stream_to


class Mirror:
    """Local copy of the portal's ZIPs, keyed by the path under /dados/."""

    def __init__(self, root: Path):
        self.root = root
        self.downloaded = 0
        self.cached = 0

    def path_for(self, url: str) -> Path:
        return self.root / url.split("/dados/", 1)[1]

    def get(self, file_entry: dict) -> Path:
        dest = self.path_for(file_entry["url"])
        stamp = dest.with_suffix(dest.suffix + ".meta")
        want = {"modified": file_entry["modified"], "size_raw": file_entry["size_raw"]}
        if dest.exists() and stamp.exists():
            try:
                if json.loads(stamp.read_text(encoding="utf-8")) == want:
                    self.cached += 1
                    return dest
            except json.JSONDecodeError:
                pass
        http_stream_to(file_entry["url"], dest)
        if not dest.exists() or dest.stat().st_size == 0:
            raise CVMPortalError(f"empty payload for {file_entry['url']}")
        stamp.write_text(json.dumps(want), encoding="utf-8")
        self.downloaded += 1
        return dest
