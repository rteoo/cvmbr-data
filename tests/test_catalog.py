"""Catalog helpers: listing parse, period overlap, dataset select/resolve."""

import json

import pytest

from cvmdata.catalog import (
    cache_dir,
    catalog_diff,
    catalog_paths,
    coverage,
    crawl_worker_count,
    listing,
    load_catalog,
    overlaps,
    parse_listing_date,
    parse_size,
    period_of,
    resolve_dataset,
    select,
    span,
)
from cvmdata.exceptions import CVMAmbiguousDatasetError, CVMCatalogError, CVMError, CVMPortalError


def test_cache_configuration_preserves_legacy_path_and_precedence(tmp_path, monkeypatch):
    monkeypatch.setenv("CVMPY_CACHE", str(tmp_path / "legacy"))
    monkeypatch.setenv("CVMDATA_CACHE", str(tmp_path / "current"))
    assert cache_dir(tmp_path / "explicit") == tmp_path / "explicit"
    assert cache_dir() == tmp_path / "current"
    monkeypatch.delenv("CVMDATA_CACHE")
    assert cache_dir() == tmp_path / "legacy"
    monkeypatch.delenv("CVMPY_CACHE")
    assert cache_dir().name == "cvmpy"


def test_crawl_worker_configuration_preserves_legacy_variable(monkeypatch):
    monkeypatch.setenv("CVMPY_CRAWL_WORKERS", "3")
    monkeypatch.setenv("CVMDATA_CRAWL_WORKERS", "4")
    assert crawl_worker_count(2) == 2
    assert crawl_worker_count() == 4
    monkeypatch.delenv("CVMDATA_CRAWL_WORKERS")
    assert crawl_worker_count() == 3


INDEX_HTML = """\
<html><head><title>Index of /dados/CIA_ABERTA/DOC/ITR/DADOS/</title></head>
<body>
<h1>Index of /dados/CIA_ABERTA/DOC/ITR/DADOS/</h1>
<pre>
<a href="../">../</a>
<a href="HIST/">HIST/</a>                                             01-Jan-2024 00:00    -
<a href="itr_cia_aberta_2024.zip">itr_cia_aberta_2024.zip</a>                         15-Mar-2026 08:00   12M
<a href="itr_cia_aberta_2025.zip">itr_cia_aberta_2025.zip</a>                         02-Apr-2026 09:15  8.5M
</pre>
</body></html>
"""


def _catalog():
    return {
        "generated_at": "2026-08-20T12:00:00+00:00",
        "source": "https://dados.cvm.gov.br/",
        "groups": {},
        "datasets": [
            {
                "path": "CIA_ABERTA/DOC/ITR",
                "area": "CIA_ABERTA",
                "title": "ITR",
                "files": [
                    {
                        "url": "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/itr_cia_aberta_2024.zip",
                        "name": "itr_cia_aberta_2024.zip",
                        "modified": "2026-03-15 08:00",
                        "size_raw": "12M",
                        "bytes": 12582912,
                        "period": "2024",
                        "archived": False,
                    }
                ],
                "meta": [],
            },
            {
                "path": "FI/DOC/INF_DIARIO",
                "area": "FI",
                "title": "Informe Diario",
                "files": [
                    {
                        "url": "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/inf_diario_fi_202608.zip",
                        "name": "inf_diario_fi_202608.zip",
                        "modified": "2026-08-20 08:00",
                        "size_raw": "40M",
                        "bytes": 41943040,
                        "period": "202608",
                        "archived": False,
                    },
                    {
                        "url": "https://dados.cvm.gov.br/dados/FI/DOC/INF_DIARIO/DADOS/HIST/inf_diario_fi_2005.zip",
                        "name": "inf_diario_fi_2005.zip",
                        "modified": "2022-03-21 00:00",
                        "size_raw": "80M",
                        "bytes": 83886080,
                        "period": "2005",
                        "archived": True,
                    },
                ],
                "meta": [],
            },
            {
                "path": "FII/DOC/INF_MENSAL",
                "area": "FII",
                "title": "FII mensal",
                "files": [],
                "meta": [],
            },
            {
                "path": "FIDC/DOC/INF_MENSAL",
                "area": "FIDC",
                "title": "FIDC",
                "files": [],
                "meta": [],
            },
        ],
        "external_packages": [],
    }


class TestParse:
    def test_listing_date(self):
        assert parse_listing_date("15-Mar-2026 08:00") == "2026-03-15 08:00"

    def test_listing_date_rejects_unknown_month(self):
        with pytest.raises(CVMPortalError):
            parse_listing_date("15-Foo-2026 08:00")

    def test_parse_size_tokens(self):
        assert parse_size("-") == 0
        assert parse_size("12M") == 12 * 1024 * 1024
        assert parse_size("8.5M") == int(8.5 * 1024 * 1024)

    def test_parse_size_rejects_garbage(self):
        with pytest.raises(CVMPortalError):
            parse_size("nope")

    def test_period_of(self):
        assert period_of("itr_cia_aberta_2024.zip") == "2024"
        assert period_of("inf_diario_fi_202608.zip") == "202608"
        assert period_of("cad_cia_aberta.csv") == ""


class TestListing:
    def test_parse_autoindex(self, monkeypatch):
        monkeypatch.setattr("cvmdata.catalog.http_get", lambda url: INDEX_HTML.encode())
        rows = listing("https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/ITR/DADOS/")
        hrefs = [r[0] for r in rows]
        assert "../" not in hrefs
        assert "HIST/" in hrefs
        assert "itr_cia_aberta_2024.zip" in hrefs

    def test_rejects_non_index(self, monkeypatch):
        monkeypatch.setattr("cvmdata.catalog.http_get", lambda url: b"<html>not an index</html>")
        with pytest.raises(CVMPortalError):
            listing("https://dados.cvm.gov.br/dados/")


class TestOverlap:
    def test_yearly_file_matches_month_inside(self):
        assert overlaps("2006", "200603", "200603") is True

    def test_yearly_file_misses_later_year(self):
        assert overlaps("2006", "200701", None) is False

    def test_monthly_file_inside_year(self):
        assert overlaps("202608", "2026", "2026") is True

    def test_empty_period_never_matches_range(self):
        assert overlaps("", "2024", "2024") is False

    def test_span_year(self):
        assert span("2006") == ("200601", "200612")


class TestSelect:
    def test_exact_path(self):
        matches = select(_catalog(), "CIA_ABERTA/DOC/ITR")
        assert [m["path"] for m in matches] == ["CIA_ABERTA/DOC/ITR"]

    def test_unique_suffix(self):
        matches = select(_catalog(), "ITR")
        assert [m["path"] for m in matches] == ["CIA_ABERTA/DOC/ITR"]

    def test_fi_fragment_is_ambiguous(self):
        matches = select(_catalog(), "FI")
        paths = {m["path"] for m in matches}
        assert "FI/DOC/INF_DIARIO" in paths
        assert "FII/DOC/INF_MENSAL" in paths
        assert "FIDC/DOC/INF_MENSAL" in paths

    def test_resolve_alias_beats_fragment(self):
        ds = resolve_dataset(_catalog(), "INF_DIARIO")
        assert ds["path"] == "FI/DOC/INF_DIARIO"

    def test_resolve_ambiguous_raises(self):
        with pytest.raises(CVMAmbiguousDatasetError):
            resolve_dataset(_catalog(), "FI")

    def test_resolve_unknown_raises(self):
        with pytest.raises(CVMError):
            resolve_dataset(_catalog(), "NO_SUCH_DATASET")

    def test_coverage_includes_hist(self):
        ds = resolve_dataset(_catalog(), "INF_DIARIO")
        assert coverage(ds) == "2005..2026-08"


class TestWorkers:
    def test_default_is_two(self, monkeypatch):
        monkeypatch.delenv("CVMDATA_CRAWL_WORKERS", raising=False)
        assert crawl_worker_count() == 2

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("CVMDATA_CRAWL_WORKERS", "1")
        assert crawl_worker_count() == 1

    def test_rejects_zero(self):
        with pytest.raises(ValueError):
            crawl_worker_count(0)


class TestCatalogFiles:
    def test_load_catalog_missing(self, tmp_path):
        with pytest.raises(CVMCatalogError):
            load_catalog(tmp_path)

    def test_catalog_diff(self, tmp_path):
        current, previous = catalog_paths(tmp_path)
        older = _catalog()
        newer = _catalog()
        newer["generated_at"] = "2026-08-21T12:00:00+00:00"
        newer["datasets"][0]["files"][0]["modified"] = "2026-08-21 08:00"
        newer["datasets"][0]["files"][0]["size_raw"] = "13M"
        previous.write_text(json.dumps(older), encoding="utf-8")
        current.write_text(json.dumps(newer), encoding="utf-8")
        diff = catalog_diff(tmp_path)
        assert diff["changed"]
        assert diff["added"] == []
        assert diff["removed"] == []
