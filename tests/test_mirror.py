"""ZIP mirror: cache hit, stamp invalidation, streamed .part write."""

import io
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from cvmpy.exceptions import CVMPortalError
from cvmpy.http import HttpClient, StreamResult
from cvmpy.mirror import Mirror


def _zip_bytes(name: str = "x.csv", text: str = "a;b\n") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zipped:
        zipped.writestr(name, text)
    return buf.getvalue()

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from cvmpy.exceptions import CVMPortalError
from cvmpy.http import HttpClient, StreamResult
from cvmpy.mirror import Mirror


def _response(content: bytes, status: int = 200, headers=None):
    class _Resp:
        status_code = status

        def __init__(self):
            self.headers = headers or {}

        def raise_for_status(self):
            if self.status_code >= 400:
                raise CVMPortalError("http error")

        def iter_content(self, chunk_size=1):
            yield content

        def close(self):
            return None

    return _Resp()


class TestMirror:
    def test_cache_hit_skips_download(self, tmp_path):
        entry = {
            "url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr.zip",
            "modified": "2026-03-15 08:00",
            "size_raw": "12M",
        }
        dest = tmp_path / "CIA_ABERTA" / "DOC" / "ITR" / "DADOS" / "itr.zip"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(_zip_bytes())
        dest.with_suffix(dest.suffix + ".meta").write_text(
            json.dumps({"modified": "2026-03-15 08:00", "size_raw": "12M"}),
            encoding="utf-8",
        )
        mirror = Mirror(tmp_path)
        with patch.object(HttpClient, "stream_to") as stream:
            got = mirror.get(entry)
        stream.assert_not_called()
        assert got == dest
        assert mirror.cached == 1
        assert mirror.downloaded == 0

    def test_redownload_when_modified_changes(self, tmp_path):
        entry = {
            "url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr.zip",
            "modified": "2026-08-20 08:00",
            "size_raw": "13M",
        }
        dest = tmp_path / "CIA_ABERTA" / "DOC" / "ITR" / "DADOS" / "itr.zip"
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b"old")
        dest.with_suffix(dest.suffix + ".meta").write_text(
            json.dumps({"modified": "2026-03-15 08:00", "size_raw": "12M"}),
            encoding="utf-8",
        )

        payload = _zip_bytes()

        def fake_stream(self, url, target: Path, **kwargs):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            return StreamResult(
                path=target, status_code=200, headers={}, byte_size=target.stat().st_size,
            )

        mirror = Mirror(tmp_path)
        with patch.object(HttpClient, "stream_to", fake_stream):
            got = mirror.get(entry)
        assert got.read_bytes() == payload
        stamp = json.loads(got.with_suffix(got.suffix + ".meta").read_text(encoding="utf-8"))
        assert stamp["modified"] == "2026-08-20 08:00"
        assert stamp["size_raw"] == "13M"
        assert stamp["sha256"]
        assert mirror.downloaded == 1

    def test_corrupt_zip_is_rejected(self, tmp_path):
        entry = {
            "url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr.zip",
            "modified": "2026-08-20 08:00",
            "size_raw": "13M",
        }

        def fake_stream(self, url, target: Path, **kwargs):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"not-a-zip")
            return StreamResult(
                path=target, status_code=200, headers={}, byte_size=target.stat().st_size,
            )

        mirror = Mirror(tmp_path)
        with patch.object(HttpClient, "stream_to", fake_stream):
            with pytest.raises(CVMPortalError, match="corrupt ZIP"):
                mirror.get(entry)
        dest = tmp_path / "CIA_ABERTA" / "DOC" / "ITR" / "DADOS" / "itr.zip"
        assert not dest.exists()

    def test_http_stream_writes_via_part(self, tmp_path, monkeypatch):
        from cvmpy import http as http_mod

        dest = tmp_path / "file.zip"
        payload = _zip_bytes()

        def fake_get(*args, **kwargs):
            assert kwargs.get("stream") is True
            return _response(payload)

        monkeypatch.setattr(http_mod.requests, "get", fake_get)
        http_mod.http_stream_to("https://example.test/file.zip", dest)
        assert dest.read_bytes() == payload
        assert not dest.with_suffix(".zip.part").exists()
