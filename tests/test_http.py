"""Portal HTTP: retries, Retry-After, 304, partial writes, circuit."""

import pytest
import requests

from cvmdata.exceptions import CVMPortalError
from cvmdata.http import HttpClient, http_get, retry_delay


class _Resp:
    def __init__(self, content=b"", status=200, headers=None):
        self.content = content
        self.status_code = status
        self.headers = headers or {}
        self.closed = False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code}")

    def iter_content(self, chunk_size=1):
        if self.status_code >= 400:
            return
        yield self.content

    def close(self):
        self.closed = True


def test_retry_after_numeric():
    assert retry_delay(0, {"retry-after": "0"}) == 0.0


def test_200_returns_bytes(monkeypatch):
    monkeypatch.setattr("cvmdata.http.requests.get", lambda *a, **k: _Resp(b"ok"))
    assert http_get("https://example.test/x") == b"ok"


def test_304_is_not_modified(monkeypatch):
    monkeypatch.setattr("cvmdata.http.requests.get", lambda *a, **k: _Resp(status=304, headers={"etag": "abc"}))
    result = HttpClient(sleep=lambda _: None).fetch_bytes("https://example.test/x", etag="abc")
    assert result.not_modified is True
    assert result.status_code == 304
    assert result.content == b""


def test_429_retries_then_succeeds(monkeypatch):
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] < 3:
            return _Resp(status=429, headers={"Retry-After": "0"})
        return _Resp(b"ok")

    monkeypatch.setattr("cvmdata.http.requests.get", fake_get)
    assert HttpClient(sleep=lambda _: None).fetch_bytes("https://example.test/x").content == b"ok"
    assert calls["n"] == 3


def test_503_exhausted_raises(monkeypatch):
    monkeypatch.setattr(
        "cvmdata.http.requests.get",
        lambda *a, **k: _Resp(status=503, headers={"retry-after": "0"}),
    )
    with pytest.raises(CVMPortalError, match="503"):
        HttpClient(retries=3, sleep=lambda _: None).fetch_bytes("https://example.test/x")


def test_404_does_not_retry(monkeypatch):
    calls = {"n": 0}

    def fake_get(*args, **kwargs):
        calls["n"] += 1
        return _Resp(status=404)

    monkeypatch.setattr("cvmdata.http.requests.get", fake_get)
    with pytest.raises(CVMPortalError, match="404"):
        HttpClient(sleep=lambda _: None).fetch_bytes("https://example.test/x")
    assert calls["n"] == 1


def test_partial_stream_cleans_part_file(tmp_path, monkeypatch):
    dest = tmp_path / "file.zip"

    def fake_get(*args, **kwargs):
        resp = _Resp(b"partial")
        def boom(chunk_size=1):
            yield b"xx"
            raise requests.ConnectionError("cut")
        resp.iter_content = boom
        return resp

    monkeypatch.setattr("cvmdata.http.requests.get", fake_get)
    with pytest.raises(CVMPortalError):
        HttpClient(retries=1, sleep=lambda _: None).stream_to("https://example.test/file.zip", dest)
    assert not dest.exists()
    assert not dest.with_suffix(".zip.part").exists()


def test_stream_304_leaves_existing(tmp_path, monkeypatch):
    dest = tmp_path / "file.zip"
    dest.write_bytes(b"cached-bytes")
    monkeypatch.setattr("cvmdata.http.requests.get", lambda *a, **k: _Resp(status=304, headers={"etag": "1"}))
    result = HttpClient(sleep=lambda _: None).stream_to(
        "https://example.test/file.zip", dest, etag="1",
    )
    assert result.not_modified is True
    assert dest.read_bytes() == b"cached-bytes"


def test_circuit_opens_after_repeated_failures(monkeypatch):
    monkeypatch.setattr(
        "cvmdata.http.requests.get",
        lambda *a, **k: _Resp(status=503, headers={"retry-after": "0"}),
    )
    client = HttpClient(retries=1, circuit_failures=2, sleep=lambda _: None)
    with pytest.raises(CVMPortalError):
        client.fetch_bytes("https://example.test/a")
    with pytest.raises(CVMPortalError):
        client.fetch_bytes("https://example.test/b")
    with pytest.raises(CVMPortalError, match="circuit open"):
        client.fetch_bytes("https://example.test/c")
