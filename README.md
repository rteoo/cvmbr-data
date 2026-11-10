# cvmdata

<p align="center">
  <img src="https://raw.githubusercontent.com/rteoo/cvmdata/main/docs/cvmdata-icon.svg" width="128" alt="cvmdata financial filing icon">
</p>

<p align="center">
  A Python client for CVM open data and RAD/ENET filings, with pandas DataFrames,
  local archive caching, and source provenance.
</p>

<p align="center">
  <a href="https://github.com/rteoo/cvmdata/actions/workflows/tests.yml"><img src="https://github.com/rteoo/cvmdata/actions/workflows/tests.yml/badge.svg" alt="Test status"></a>
  <a href="pyproject.toml"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10 or newer"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT license"></a>
</p>

Fetch Brazilian company statements, fund disclosures, and registration data from
the [Portal de Dados Abertos CVM](https://dados.cvm.gov.br/), or query
[RAD/ENET](https://www.rad.cvm.gov.br/ENETWeb/frmConsultaExternaCVM.aspx)
for company filings, without an API key. This is an independent client, not an
official CVM product. Bulk datasets and live filings are separate publication
surfaces; the library does not guarantee their synchronization or freshness.

## Highlights

- pandas DataFrames for ITR, DFP, fund `INF_DIARIO`, CDA, and other CVM datasets.
- Catalog discovery includes historical `DADOS/HIST/` archives and curated aliases.
- Local ZIP mirroring avoids duplicate downloads when catalog stamps are unchanged.
- CVM CSV handling: latin-1, semicolon delimiters, highest `VERSAO`, `ORDEM_EXERC`,
  and CNPJ or `CD_CVM` matching.
- Source descriptors with SHA-256, exact byte size, URL, HTTP headers, and parser version.
- RAD/ENET listing and document downloads with a protocol/version manifest.

## Installation

```bash
pip install git+https://github.com/rteoo/cvmdata.git
```

Or from source:

```bash
git clone https://github.com/rteoo/cvmdata.git
cd cvmdata
pip install .
```

### Requirements

- Python 3.10+
- pandas
- requests

## Quick Start

```python
from cvmdata import refresh_catalog, fetch, fetch_itr, list_filings, download_filings

refresh_catalog()

dre = fetch("ITR", start="2024", end="2026", company="15423", table="DRE_con")
print(dre.head())

cota = fetch("INF_DIARIO", start="202608", company="28.152.872/0001-77")
print(cota)

docs = list_filings(codigo_cvm=15423, date_from="2026-01-01", date_to="2026-08-20")
download_filings(docs, out="./filings")
```

## API Reference

### Catalog

The portal is a CKAN catalog over a directory autoindex. CKAN alone misses `DADOS/HIST/` (multi-GB archives). Call `refresh_catalog()` before trusting `list_datasets` or `fetch`.

#### `refresh_catalog(cache_dir_path=None, workers=None)`

Crawl `https://dados.cvm.gov.br/dados/` (including `HIST/`), merge CKAN titles, and write `catalog.json` to the cache directory. Default concurrency is two requests per host (`CVMDATA_CRAWL_WORKERS` or `workers=`).

#### `list_datasets(area=None, grep=None)`

Return dataset stats: path, file count, bytes, coverage span, last update, title.

#### `show_dataset(dataset)` / `dataset_urls(dataset, start=None, end=None)` / `catalog_diff()`

Inspect one dataset, list download URLs, or diff against the previous refresh.

`<dataset>` is a curated alias (`ITR`, `INF_DIARIO`), a full path (`CIA_ABERTA/DOC/ITR`), or a unique suffix. Ambiguous fragments raise `CVMAmbiguousDatasetError` instead of guessing.

### Fetch

#### `fetch(dataset, start=None, end=None, company=None, table=None, ordem="ultimo", keep_all_versions=False)`

Mirror matching ZIPs (re-download only when the catalog stamp changes), stream the CSVs inside, and apply hygiene.

- With `table` (substring of the member name, e.g. `DRE_con`): one DataFrame.
- Without `table`: `dict[str, DataFrame]`, one frame per table.
- `company` accepts a CVM code or CNPJ (punctuation and leading zeros ignored); repeatable as a list.
- `start` / `end` are `yyyy` or `yyyymm`. Yearly files still match a monthly window that lands inside them.
- `INF_DIARIO` and `CDA` require a period window (they are too large to materialize whole). Use `iter_rows` for warehouse-scale ingest.
- DataFrame `.attrs` carry `source`, `table`, `ingested_at`, and source URLs.

```python
from cvmdata import fetch, fetch_itr, DATASETS

dre = fetch_itr(start="2024", company="15423", table="DRE_con")
print(DATASETS["ITR"])  # CIA_ABERTA/DOC/ITR
```

Convenience wrappers: `fetch_itr`, `fetch_dfp`, `fetch_inf_diario`, `fetch_cda`, `fetch_cadastro`.

#### `fetch_source_objects(dataset, start=None, end=None)`

Mirror matching ZIPs (no duplicate download when the catalog stamp is unchanged) and return `SourceObjectMeta` records: SHA-256, exact byte size, source URL, local path, fetch time, HTTP headers, library version, and parser version `cvm-csv-latin1-1`. Import this from `cvmdata`, not from `cvmdata.mirror`.

#### `iter_rows(...)` / `iter_archive_rows(payload)` / `list_tables(dataset)`

Row generator over mirrored archives, row generator over a ZIP/CSV already in memory (warehouse replay), and table/column inventory of the newest matching archive.

### RAD/ENET filings

Query RAD/ENET directly when you need filings that may not yet appear in bulk datasets.

#### `list_filings(codigo_cvm, date_from, date_to, all_docs=True)`

Dates accept `YYYY-MM-DD` or `DD/MM/YYYY`. Default includes structured documents and IPE; `all_docs=False` is IPE-only. Inactive/canceled versions are dropped.

#### `download_filings(docs, out)`

Cookie-primes the ENET session, writes PDF/ZIP/text files, rejects HTML shells, and merges a `manifest-cvm-<from>-<to>.csv` by protocol+version. Files already on disk are reported as `cached`.

### Exceptions

- `CVMError` — base
- `CVMPortalError` — portal response this client cannot trust
- `CVMEmptyResponseError` — no files or no rows
- `CVMAmbiguousDatasetError` — needle matched more than one dataset
- `CVMCatalogError` — local catalog missing

### Cache

Default: `%LOCALAPPDATA%/cvmpy` on Windows, `~/.cache/cvmpy` elsewhere. The existing
cache directory is deliberately preserved during the rename. Override it with
`cache_dir_path=` or `CVMDATA_CACHE`; the legacy `CVMPY_CACHE` variable is also
accepted. Explicit function arguments take precedence, followed by the new
environment variable, then the legacy variable.

### Migrating from the private cvmpy client

Change imports from `cvmpy` to `cvmdata` and update source-install URLs to
`https://github.com/rteoo/cvmdata`. The unrelated `cvmpy` project on PyPI is not
this client; `cvmdata` does not install a competing `cvmpy` import package.
`CVMPY_CACHE` and `CVMPY_CRAWL_WORKERS` remain supported, with the corresponding
`CVMDATA_*` variables taking precedence. See [release preparation](docs/releasing.md).

## API Limits

- **Large fund datasets:** `fetch("INF_DIARIO")` and `fetch("CDA")` require a
  `start` or `end` window. Use `iter_rows` for ingestion without materializing a
  whole dataset as DataFrames.
- **Date windows:** bulk periods are `yyyy` or `yyyymm`; RAD/ENET dates accept
  `YYYY-MM-DD` or `DD/MM/YYYY`.
- **Catalog:** refresh explicitly to discover changed files; cached data is not
  a guarantee of current portal contents.
- **Filings:** RAD/ENET availability and portal format can change. HTML download
  shells are rejected rather than saved as documents.
- **Scope:** this is a library, with no CLI. CVM legislation is outside its scope.

## Project Structure

```text
cvmdata/
├── cvmdata/
│   ├── __init__.py      # Public API exports
│   ├── artifacts.py     # SourceObjectMeta descriptors and checksums
│   ├── catalog.py       # CKAN and autoindex discovery, including HIST/
│   ├── client.py        # DataFrames, row iterators, and convenience wrappers
│   ├── datasets.py      # Curated dataset aliases
│   ├── filings.py       # RAD/ENET listing, downloads, and manifests
│   ├── http.py          # HTTP, finite retries, and streamed downloads
│   ├── hygiene.py       # CSV, version, company, and accounting filters
│   └── mirror.py        # Local archive caching
├── docs/
│   └── cvmdata-icon.svg   # Editable project icon
├── tests/               # Mocked unit tests and opt-in live tests
├── pyproject.toml       # Packaging and test configuration
├── CVM_DATA_REFERENCE.md
└── README.md
```

## Development

```bash
pip install -e ".[dev]"
python -m pytest -m "not integration"
python -m build
```

Integration tests contact the live CVM portals and are excluded from CI. Run
them deliberately with `python -m pytest tests/test_integration.py -m integration`
when network access and live portal validation are intended. Offline tests do
not establish current portal availability.

## Data Source

Bulk data comes from the [CVM Open Data Portal](https://dados.cvm.gov.br/).
Company filings come from [RAD/ENET](https://www.rad.cvm.gov.br/ENETWeb/frmConsultaExternaCVM.aspx).
See [CVM_DATA_REFERENCE.md](CVM_DATA_REFERENCE.md) for dataset and parser details.

## License

Code is MIT. CVM datasets and RAD documents remain works of the Comissão de Valores Mobiliários — see `LICENSE`.
