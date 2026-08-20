"""ZIP mirror: cache hit, stamp invalidation, streamed .part write."""

import json
from pathlib import Path
from unittest.mock import patch

from cvmpy.exceptions import CVMPortalError
from cvmpy.mirror import Mirror


def _response(content: bytes, status: int = 200):
    class _Resp:
        status_code = status
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
        dest.write_bytes(b"PK\x03\x04cached")
        dest.with_suffix(dest.suffix + ".meta").write_text(
            json.dumps({"modified": "2026-03-15 08:00", "size_raw": "12M"}),
            encoding="utf-8",
        )
        mirror = Mirror(tmp_path)
        with patch("cvmpy.mirror.http_stream_to") as stream:
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

        def fake_stream(url, target: Path, **kwargs):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"PK\x03\x04new")

        mirror = Mirror(tmp_path)
        with patch("cvmpy.mirror.http_stream_to", side_effect=fake_stream):
            got = mirror.get(entry)
        assert got.read_bytes() == b"PK\x03\x04new"
        stamp = json.loads(got.with_suffix(got.suffix + ".meta").read_text(encoding="utf-8"))
        assert stamp == {"modified": "2026-08-20 08:00", "size_raw": "13M"}
        assert mirror.downloaded == 1

    def test_http_stream_writes_via_part(self, tmp_path, monkeypatch):
        from cvmpy import http as http_mod

        dest = tmp_path / "file.zip"
        payload = b"PK" + b"x" * 1000

        def fake_get(*args, **kwargs):
            assert kwargs.get("stream") is True
            return _response(payload)

        monkeypatch.setattr(http_mod.requests, "get", fake_get)
        http_mod.http_stream_to("https://example.test/file.zip", dest)
        assert dest.read_bytes() == payload
        assert not dest.with_suffix(".zip.part").exists()
