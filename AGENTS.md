# AGENTS.md

Canonical agent contract for this repository — it guides Claude Code, Codex, and any other coding agent. `CLAUDE.md` is a single `@AGENTS.md` import so Claude Code auto-loads these rules; make all edits here, never fork guidance into `CLAUDE.md`.

## Project

`cvmpy` is a Python client library for **CVM open data** (`dados.cvm.gov.br`) and live **RAD/ENET** filings. It crawls the portal autoindex (including `DADOS/HIST/`), mirrors ZIPs locally, applies CVM CSV hygiene (latin-1, `ORDEM_EXERC`, highest `VERSAO`, company/CNPJ match), and returns pandas DataFrames. Public API (`cvmpy/__init__.py`): `refresh_catalog`, `list_datasets`, `fetch`, `fetch_itr` / `fetch_dfp` / `fetch_inf_diario` / `fetch_cda` / `fetch_cadastro`, `fetch_source_objects`, `iter_archive_rows`, `SourceObjectMeta`, `PARSER_VERSION`, `iter_rows`, `list_filings`, `download_filings`, plus `CVMError` and subclasses. Library only — no CLI, no `__main__`. Legislation (`conteudo.cvm.gov.br`) is out of scope.

## Stack

- Python `>=3.10` (classifiers cover 3.10–3.13). Runtime deps: `pandas>=1.5`, `requests>=2.28`.
- Packaging: PEP 621 `pyproject.toml`, setuptools + wheel. Dev extra (`.[dev]`): `pytest>=7.0`, `build>=1.0`, `twine>=4.0`.
- No lint / formatter / type-checker tooling exists (no ruff/flake8/black/mypy config or deps). Annotations are present; do not add a type-checker unless asked.

## Commands

```bash
pip install -e ".[dev]"                              # local dev setup (there is NO requirements.txt)
pytest                                               # full suite
pytest -m "not integration"                          # offline/CI-safe subset (unit only)
pytest tests/test_integration.py -m integration      # live portal tests — network, opt-in, may be slow
python -m build                                      # build sdist+wheel
```

- CVM portals are public/unauthenticated — no API key.
- Integration tests hit **live** `dados.cvm.gov.br` and `rad.cvm.gov.br`. Exclude them by default; never run them during automated/agentic edits without explicit instruction.

## Architecture

- `cvmpy/constants.py` — portal URLs, encodings, timeouts, crawl workers (default 2), unbounded-dataset paths.
- `cvmpy/exceptions.py` — `CVMError` hierarchy.
- `cvmpy/datasets.py` — curated `DATASETS` aliases (`ITR` → `CIA_ABERTA/DOC/ITR`, …). Hand-curated, not generated.
- `cvmpy/http.py` — `requests` GET with Retry-After, 429/503 backoff, 304, circuit; streaming ZIP download.
- `cvmpy/catalog.py` — CKAN + `/dados/` autoindex crawl including `HIST/`; `refresh_catalog` / `list_datasets` / `catalog_diff`.
- `cvmpy/artifacts.py` — public `SourceObjectMeta` descriptors.
- `cvmpy/mirror.py` — disk cache invalidated on catalog `(modified, size_raw)`; SHA-256 stamps.
- `cvmpy/hygiene.py` — latin-1 `;` CSV, company keys, `ORDEM_EXERC`, highest `VERSAO`.
- `cvmpy/client.py` — `fetch` / `iter_rows` / `fetch_source_objects` / `iter_archive_rows` / convenience wrappers.
- `cvmpy/filings.py` — RAD/ENET `list_filings` / `download_filings` via `requests.Session`.
- `cvmpy/__init__.py` — public re-exports; keep `__all__` in sync.

Load-bearing behavior to preserve:

- Crawl `DADOS/HIST/` or deep archives vanish.
- Period overlap is an interval, not a point: yearly `2006` must match `start="200603"`.
- Autoindex `size_raw` tokens are approximate — compare the token, never parsed bytes, for cache invalidation.
- Highest `VERSAO` when the column exists (VLMO restates in-place; ITR/FRE often do not).
- Default `ORDEM_EXERC` is `ÚLTIMO`. Never mix `con` and `ind` in one series.
- `fetch("INF_DIARIO")` / `fetch("CDA")` without `start`/`end` must raise. `iter_rows` may be unbounded.
- Dataset aliases resolve first; ambiguous fragments (`FI`) raise `CVMAmbiguousDatasetError`.
- ENET structured downloads need a session that visited the consulta page. A `200 text/html` body is a failed download, never a filing.
- Dual dates on RAD (`YYYY-MM-DD` and `DD/MM/YYYY`). Period filters on bulk fetch stay `yyyy` / `yyyymm`.
- Cache default: `%LOCALAPPDATA%/cvmpy` or `~/.cache/cvmpy`, override with `cache_dir=` or `CVMPY_CACHE`.

## Testing Conventions

pytest under `tests/`; classes `Test*`, methods `test_*`. The `integration` marker is registered in `pyproject.toml`. No coverage tooling.

- Unit tests mock `requests.get` / `requests.Session` or seed a temp cache with ZIPs + catalog JSON.
- New client functions get a mocked unit test and, if they hit the network, a matching `@pytest.mark.integration` test.
- Dataset aliases: keys `UPPER_SNAKE_CASE`, values unique paths — enforced by `tests/test_datasets.py`.

## Release & CI

- **Test CI:** `.github/workflows/tests.yml` runs `pytest -m "not integration"` on Python 3.10–3.13 for every push and PR to `main`.
- Version is dynamic — `pyproject.toml` reads `cvmpy.__version__`. A release bumps only `__version__`, adds a `CHANGELOG.md` entry, and pushes a matching `v*` tag.
- Canonical repo is `github.com/rteoo/cvmpy`.

## Git

Default branch `main`. Conventional-commit-style messages (`feat:`, `fix:`, `chore:`, `release:`). No AI attribution in commit messages.
