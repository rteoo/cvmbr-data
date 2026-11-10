# CVM data reference

Developer notes for the CVM surfaces that `cvmdata` implements. Authoritative files live at [dados.cvm.gov.br](https://dados.cvm.gov.br/) and [rad.cvm.gov.br](https://www.rad.cvm.gov.br/). Legislation (`conteudo.cvm.gov.br`) is **not** in this package.

## Two surfaces

| Question | Source | Client |
|---|---|---|
| Every listed company's DRE for 2024; fund NAV series; who owns what | Bulk CSV ZIPs | `refresh_catalog` + `fetch` |
| Company X's fatos relevantes from this week | Live ENET | `list_filings` / `download_filings` |

Open data lags live RAD/ENET by roughly 1–2 days. Always say which source was used. Do not mix them in one series.

## URL layout (open data)

```text
https://dados.cvm.gov.br/dados/<AREA>/<CAD|DOC|EVENTOS|...>/<SET>/DADOS/<file>
                                                            .../DADOS/HIST/<older file>
                                                            .../META/meta_<set>.txt
```

CKAN (`/api/3/action/current_package_list_with_resources`) is metadata only. It lists recent years; **`DADOS/HIST/` is not in CKAN**. A crawl that stops at `DADOS/` silently drops multi-GB archives (for example FI balancetes before 2015).

External CKAN packages (ofertas públicas spreadsheets, arrecadação) point at gov.br ODS files outside `/dados/`. `refresh_catalog()` records them as `external_packages` and does not crawl them.

## File conventions

- Delimiter `;`, encoding **latin-1**. Decoding as UTF-8 mangles every accent.
- Join key: `CNPJ_CIA` / `CNPJ_Companhia` / `CNPJ_FUNDO` and `CD_CVM` / `Codigo_CVM`. Tickers live in `cad_cia_aberta.csv`, not in every table.
- `ORDEM_EXERC` is `ÚLTIMO` / `PENÚLTIMO` — one ITR/DFP file holds both periods. `fetch` defaults to `ÚLTIMO`.
- `ESCALA_MOEDA` states whether `VL_CONTA` is in units or thousands.
- `VERSAO` increments on refiling. Keep the highest version per (`CNPJ`, `DT_REFER`, doc) or restatements appear as duplicate rows. ITR/FRE often publish only the current version (dedup is a no-op). VLMO restates in-place — skipping dedup double-counts insider positions.
- `con` = consolidado, `ind` = individual. Never mix them in one series. Table names keep the suffix (`DRE_con`).
- Period in file names is `yyyy` (ITR) or `yyyymm` (INF_DIARIO). Interval overlap: a yearly 2006 ZIP still matches `start="200603"`.

Autoindex size tokens are rounded to three significant digits. Cache invalidation compares the raw token plus mtime, not parsed bytes.

## Curated aliases

See `cvmdata.DATASETS`. Important paths:

| Alias | Path | Notes |
|---|---|---|
| `CAD` | `CIA_ABERTA/CAD` | Daily snapshot, CNPJ ↔ código CVM ↔ ticker context |
| `ITR` | `CIA_ABERTA/DOC/ITR` | Quarterly statements, 2011– |
| `DFP` | `CIA_ABERTA/DOC/DFP` | Annual statements, 2010– |
| `FRE` | `CIA_ABERTA/DOC/FRE` | Ownership, compensation, related parties |
| `FCA` | `CIA_ABERTA/DOC/FCA` | Cadastral form |
| `IPE` | `CIA_ABERTA/DOC/IPE` | Filing index + `Link_Download`, 2003– |
| `VLMO` | `CIA_ABERTA/DOC/VLMO` | Art. 11 holdings — **dedup VERSAO** |
| `INF_DIARIO` | `FI/DOC/INF_DIARIO` | Cota, PL, captação, resgate, cotistas. Months M and M-1 update Mon–Sat 08:00 BRT |
| `CDA` | `FI/DOC/CDA` | Portfolio look-through; confidential holdings in `*_CONFID_*` |
| `FI_CAD` | `FI/CAD` | Fund cadastro, last business day |

`FI` as a needle is ambiguous (`FII`, `FIDC`, `FIAGRO`, `FIE`, `FIP`). Use an alias or a full path.

`fetch("INF_DIARIO")` and `fetch("CDA")` without `start`/`end` raise — those tables are too large to materialize. `iter_rows` has no such guard.

## RAD/ENET protocol

1. GET `frmConsultaExternaCVM.aspx?codigoCVM=<code>` to seed the ASP.NET cookie.
2. POST JSON to `.../ListarDocumentos` with `empresa=",{code:06d}"`, `periodo="2"`, `dataDe`/`dataAte` as `DD/MM/YYYY`, `categoria` `EST_-1,IPE_-1_-1_-1` (or IPE-only).
3. `d.dados` is a string table: rows `&*`, fields `$&`. Keep field 7 `Ativo`.
4. Download params from `OpenDownloadDocumentos(seq, ver, protocolo, descTipo)` in field 10.
5. Structured ITR/DFP/FRE/FCA ZIPs are served only to a primed session. An HTML body is a failure, never a document. Informe do Código de Governança may arrive as `;`-delimited text.

File names: `YYYY-MM-DD-TYPE-topic.ext`. On slug collision, append `-p<protocolo>` — distinct documents must not look like versions of each other.

## Cadence (producer policy)

| Dataset | Update |
|---|---|
| Catalog / cadastros | Daily |
| `INF_DIARIO` M and M-1 | Mon–Sat 08:00 BRT |
| `INF_DIARIO` M-2…M-11 | Weekly |
| CDA recent months | Daily; older weekly |
| ITR / DFP | After earnings; restatements land as new `VERSAO` |

This library does not schedule jobs. A downstream application or scheduler should call `refresh_catalog` then `fetch` / `list_filings`.
