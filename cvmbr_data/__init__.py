"""
cvmbr_data — Python client for CVM open data and live RAD/ENET filings.

Usage:
    from cvmbr_data import refresh_catalog, fetch, fetch_itr, list_filings

    refresh_catalog()
    dre = fetch("ITR", start="2024", company="15423", table="DRE_con")

    docs = list_filings(codigo_cvm=15423, date_from="2026-01-01", date_to="2026-08-20")
"""

__version__ = "0.3.0"

from .artifacts import SourceObjectMeta, build_source_meta
from .catalog import (
    cache_dir,
    catalog_diff,
    dataset_urls,
    list_datasets,
    load_catalog,
    refresh_catalog,
    show_dataset,
)
from .client import (
    fetch,
    fetch_cadastro,
    fetch_cda,
    fetch_dfp,
    fetch_inf_diario,
    fetch_itr,
    fetch_source_objects,
    iter_archive_rows,
    iter_rows,
    list_tables,
)
from .constants import PARSER_VERSION
from .datasets import (
    ALL_DATASETS,
    CATEGORIES,
    CIA_ABERTA,
    DATASETS,
    ESTRUTURADOS,
    FUNDOS,
    REGISTROS,
    SECURITIZADORAS,
)
from .exceptions import (
    CVMAmbiguousDatasetError,
    CVMCatalogError,
    CVMEmptyResponseError,
    CVMError,
    CVMPortalError,
)
from .filings import download_filings, list_filings

__all__ = [
    "__version__",
    "refresh_catalog",
    "load_catalog",
    "list_datasets",
    "show_dataset",
    "dataset_urls",
    "catalog_diff",
    "cache_dir",
    "fetch",
    "fetch_itr",
    "fetch_dfp",
    "fetch_inf_diario",
    "fetch_cda",
    "fetch_cadastro",
    "fetch_source_objects",
    "iter_archive_rows",
    "iter_rows",
    "list_tables",
    "list_filings",
    "download_filings",
    "SourceObjectMeta",
    "build_source_meta",
    "PARSER_VERSION",
    "CVMError",
    "CVMPortalError",
    "CVMEmptyResponseError",
    "CVMAmbiguousDatasetError",
    "CVMCatalogError",
    "DATASETS",
    "ALL_DATASETS",
    "CATEGORIES",
    "CIA_ABERTA",
    "FUNDOS",
    "ESTRUTURADOS",
    "SECURITIZADORAS",
    "REGISTROS",
]
