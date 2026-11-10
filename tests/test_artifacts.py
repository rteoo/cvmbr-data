"""Public source-object API — no import of cvmbr_data.mirror required."""

import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from cvmbr_data import SourceObjectMeta, build_source_meta, fetch_source_objects
from cvmbr_data.catalog import catalog_paths
from cvmbr_data.constants import PARSER_VERSION
from cvmbr_data.http import HttpClient, StreamResult


def _zip(payload: bytes) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zipped:
        zipped.writestr("x.csv", payload)
    return buf.getvalue()


def test_source_meta_default_timestamp_is_utc(tmp_path):
    payload = tmp_path / "source.csv"
    payload.write_bytes(b"CNPJ_CIA;VL\n1;2\n")
    before = datetime.now(timezone.utc)

    meta = build_source_meta(
        payload,
        source_url="https://dados.cvm.gov.br/dados/source.csv",
        catalog_modified="2026-08-20 12:00",
        catalog_size_raw="1K",
    )

    assert meta.fetched_at.tzinfo is timezone.utc
    assert before <= meta.fetched_at <= datetime.now(timezone.utc)


def test_fetch_source_objects_from_cache(tmp_path):
    payload = _zip(b"CNPJ_CIA;VL\n1;2\n")
    url = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_2024.zip"
    catalog = {
        "generated_at": "2026-08-20T12:00:00+00:00",
        "source": "https://dados.cvm.gov.br/",
        "groups": {},
        "datasets": [{
            "path": "CIA_ABERTA/DOC/ITR",
            "area": "CIA_ABERTA",
            "title": "ITR",
            "files": [{
                "url": url,
                "name": "itr_cia_aberta_2024.zip",
                "modified": "2026-03-15 08:00",
                "size_raw": "1M",
                "bytes": 1024,
                "period": "2024",
                "archived": False,
            }],
            "meta": [],
        }],
        "external_packages": [],
    }
    current, _ = catalog_paths(tmp_path)
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text(json.dumps(catalog), encoding="utf-8")
    dest = tmp_path / "mirror" / "CIA_ABERTA" / "DOC" / "ITR" / "DADOS" / "itr_cia_aberta_2024.zip"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    dest.with_suffix(dest.suffix + ".meta").write_text(
        json.dumps({"modified": "2026-03-15 08:00", "size_raw": "1M"}),
        encoding="utf-8",
    )
    with patch.object(HttpClient, "stream_to") as stream:
        rows = fetch_source_objects("ITR", start="2024", cache_dir_path=tmp_path)
    stream.assert_not_called()
    assert len(rows) == 1
    meta = rows[0]
    assert isinstance(meta, SourceObjectMeta)
    assert meta.sha256 == hashlib.sha256(payload).hexdigest()
    assert meta.byte_size == len(payload)
    assert meta.source_url == url
    assert Path(meta.local_path) == dest
    assert meta.cached is True
    assert meta.parser_version == PARSER_VERSION
    assert meta.library_version
    assert meta.catalog_modified == "2026-03-15 08:00"


def test_fetch_source_objects_records_download(tmp_path):
    payload = _zip(b"a")
    url = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_2024.zip"
    catalog = {
        "generated_at": "2026-08-20T12:00:00+00:00",
        "source": "https://dados.cvm.gov.br/",
        "groups": {},
        "datasets": [{
            "path": "CIA_ABERTA/DOC/ITR",
            "area": "CIA_ABERTA",
            "title": "ITR",
            "files": [{
                "url": url,
                "name": "itr_cia_aberta_2024.zip",
                "modified": "2026-03-15 08:00",
                "size_raw": "1M",
                "bytes": 1024,
                "period": "2024",
                "archived": False,
            }],
            "meta": [],
        }],
        "external_packages": [],
    }
    current, _ = catalog_paths(tmp_path)
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text(json.dumps(catalog), encoding="utf-8")

    def fake_stream(self, target_url, dest, **kwargs):
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        return StreamResult(
            path=dest, status_code=200, headers={"etag": "w1"}, byte_size=len(payload),
        )

    with patch.object(HttpClient, "stream_to", fake_stream):
        rows = fetch_source_objects("ITR", cache_dir_path=tmp_path)
    assert rows[0].cached is False
    assert rows[0].sha256 == hashlib.sha256(payload).hexdigest()
    stamp = json.loads(Path(rows[0].local_path).with_suffix(".zip.meta").read_text(encoding="utf-8"))
    assert stamp["sha256"] == rows[0].sha256
    assert stamp["etag"] == "w1"
