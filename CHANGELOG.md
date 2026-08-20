# Changelog

## [v0.2.0] - 2026-08-20

### Added
- Public warehouse descriptors: `SourceObjectMeta`, `build_source_meta`, `fetch_source_objects` (SHA-256, byte size, mirrored path, fetch time, HTTP headers, library/parser version). Callers import these from `cvmpy`, not `cvmpy.mirror`.
- `iter_archive_rows` parses a ZIP or latin-1 CSV payload already in memory (no portal contact) with the same hygiene as `iter_rows`.
- Conditional ZIP downloads (`If-None-Match` / `If-Modified-Since`) and `304` cache reuse.
- Configurable catalog crawl concurrency via `refresh_catalog(workers=…)` or `CVMPY_CRAWL_WORKERS`.

### Changed
- Default portal crawl concurrency is 2 (was 12).
- HTTP GET/stream honors `Retry-After`, retries 429/503 (and other 5xx) with finite exponential backoff and jitter, and opens a circuit after repeated exhausted failures.
- Mirror stamps store checksum metadata; corrupt ZIP payloads are rejected and not stamped.

## [v0.1.0] - 2026-08-20

### Added
- Initial `cvmpy` client for CVM open data (`dados.cvm.gov.br`) and live RAD/ENET filings.
- Catalog crawl that merges CKAN metadata with the `/dados/` autoindex, including `DADOS/HIST/`.
- Streaming ZIP mirror with `(modified, size_raw)` invalidation and CVM CSV hygiene (latin-1, `ORDEM_EXERC`, highest `VERSAO`, CNPJ/`CD_CVM` match).
- `fetch` / `iter_rows` returning pandas DataFrames (or a dict of tables) plus convenience wrappers for ITR, DFP, INF_DIARIO, CDA, and company cadastro.
- RAD/ENET `list_filings` and `download_filings` on `requests.Session` (cookie-primed, HTML-shell rejected, protocol+version manifest).
