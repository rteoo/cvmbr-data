# cvmpy

Python client for **CVM open data** from the [Portal de Dados Abertos CVM](https://dados.cvm.gov.br/) and live **RAD/ENET** filings.

Fetch bulk structured datasets (ITR, DFP, fund `INF_DIARIO`, CDA, …) as pandas DataFrames, with CVM file hygiene applied: latin-1, highest `VERSAO`, `ORDEM_EXERC` filter, and CNPJ/`CD_CVM` matching. Open data lags live RAD/ENET by about 1–2 days — use `list_filings` when you need what a company published today.

## Installation

```bash
pip install cvmpy
```

Or from source:

```bash
git clone https://github.com/rteoo/cvmpy.git
cd cvmpy
pip install .
```

### Requirements

- Python 3.10+
- pandas
- requests

## Quick Start

```python
from cvmpy import refresh_catalog, fetch, fetch_itr, list_filings, download_filings

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

#### `refresh_catalog(cache_dir_path=None)`

Crawl `https://dados.cvm.gov.br/dados/` (including `HIST/`), merge CKAN titles, and write `catalog.json` to the cache directory.

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
from cvmpy import fetch, fetch_itr, DATASETS

dre = fetch_itr(start="2024", company="15423", table="DRE_con")
print(DATASETS["ITR"])  # CIA_ABERTA/DOC/ITR
```

Convenience wrappers: `fetch_itr`, `fetch_dfp`, `fetch_inf_diario`, `fetch_cda`, `fetch_cadastro`.

#### `iter_rows(...)` / `list_tables(dataset)`

Row generator (no DataFrame) and table/column inventory of the newest matching archive.

### RAD/ENET filings

Open data is the panel. For “what did this company file today?”, query live ENET.

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

Default: `%LOCALAPPDATA%/cvmpy` on Windows, `~/.cache/cvmpy` elsewhere. Override with `cache_dir_path=` on any function or the `CVMPY_CACHE` environment variable.

## License

Code is MIT. CVM datasets and RAD documents remain works of the Comissão de Valores Mobiliários — see `LICENSE`.
