# Changelog

## [v0.1.0] - 2026-08-20

### Added
- Initial `cvmpy` client for CVM open data (`dados.cvm.gov.br`) and live RAD/ENET filings.
- Catalog crawl that merges CKAN metadata with the `/dados/` autoindex, including `DADOS/HIST/`.
- Streaming ZIP mirror with `(modified, size_raw)` invalidation and CVM CSV hygiene (latin-1, `ORDEM_EXERC`, highest `VERSAO`, CNPJ/`CD_CVM` match).
- `fetch` / `iter_rows` returning pandas DataFrames (or a dict of tables) plus convenience wrappers for ITR, DFP, INF_DIARIO, CDA, and company cadastro.
- RAD/ENET `list_filings` and `download_filings` on `requests.Session` (cookie-primed, HTML-shell rejected, protocol+version manifest).
