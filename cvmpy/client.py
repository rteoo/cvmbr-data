"""Fetch CVM open-data tables as pandas DataFrames."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from .catalog import (
    cache_dir,
    load_catalog,
    resolve_dataset,
    selected_files,
)
from .constants import UNBOUNDED_PATHS
from .exceptions import CVMEmptyResponseError, CVMError
from .hygiene import (
    ORDEM_CHOICES,
    VERSION_COLUMNS,
    best_versions,
    company_key,
    find_column,
    keep_row,
    members,
    norm,
    read_header,
    rows_of,
    table_key,
)
from .mirror import Mirror


def _normalize_period(value: str | None) -> str | None:
    """Accept yyyy, yyyymm, YYYY-MM, or YYYY-MM-DD; store as yyyy or yyyymm."""
    if value is None:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) == 4:
        return digits
    if len(digits) >= 6:
        month = digits[4:6]
        if not (1 <= int(month) <= 12):
            raise ValueError(f"invalid period {value!r}; use yyyy or yyyymm")
        return digits[:6]
    raise ValueError(f"invalid period {value!r}; use yyyy or yyyymm")


def _wanted_companies(company) -> set[str] | None:
    if company is None:
        return None
    if isinstance(company, (str, int)):
        values = [company]
    else:
        values = list(company)
    if not values:
        return None
    return {company_key(str(v)) for v in values}


def _require_window(path: str, start: str | None, end: str | None) -> None:
    if path in UNBOUNDED_PATHS and not (start or end):
        raise CVMError(
            f"{path} is too large to fetch without a period; pass start= and/or end= "
            "(yyyy or yyyymm), or use iter_rows() for warehouse ingest"
        )


def _stamp(frame: pd.DataFrame, *, dataset: str, table: str, files: list[dict], ingested_at: str) -> pd.DataFrame:
    frame.attrs["source"] = dataset
    frame.attrs["table"] = table
    frame.attrs["ingested_at"] = ingested_at
    frame.attrs["files"] = [f["url"] for f in files]
    frame.attrs["producer_modified"] = [f.get("modified", "") for f in files]
    return frame


def list_tables(
    dataset: str,
    start: str | None = None,
    end: str | None = None,
    table: str | None = None,
    cache_dir_path: str | Path | None = None,
) -> list[dict]:
    """Table names and column counts in the newest matching archive."""
    start = _normalize_period(start)
    end = _normalize_period(end)
    cache = cache_dir(cache_dir_path)
    catalog = load_catalog(cache)
    ds = resolve_dataset(catalog, dataset)
    files = selected_files(ds, start, end)
    if not files:
        raise CVMEmptyResponseError(f"{ds['path']} has no files for the requested period")
    mirror = Mirror(cache / "mirror")
    archive = mirror.get(files[-1])
    prefix = re.sub(r"_((?:19|20)\d{2}(?:0[1-9]|1[0-2])?)$", "", Path(archive).stem)
    rows = []
    for member in members(archive, table):
        header = read_header(archive, member)
        rows.append({
            "table": table_key(member, prefix),
            "member": member,
            "columns": len(header),
            "header": header,
            "archive": files[-1]["name"],
        })
    return rows


def iter_rows(
    dataset: str,
    start: str | None = None,
    end: str | None = None,
    company=None,
    table: str | None = None,
    ordem: str = "ultimo",
    keep_all_versions: bool = False,
    cache_dir_path: str | Path | None = None,
):
    """Yield filtered row dicts without materializing a DataFrame."""
    start = _normalize_period(start)
    end = _normalize_period(end)
    if ordem not in ORDEM_CHOICES and ordem != "all":
        raise ValueError("ordem must be 'ultimo', 'penultimo', or 'all'")
    cache = cache_dir(cache_dir_path)
    catalog = load_catalog(cache)
    ds = resolve_dataset(catalog, dataset)
    files = selected_files(ds, start, end)
    if not files:
        raise CVMEmptyResponseError(f"{ds['path']} has no files for the requested period")
    wanted = _wanted_companies(company)
    ordem_value = None if ordem == "all" else ORDEM_CHOICES[ordem]
    mirror = Mirror(cache / "mirror")

    for entry in files:
        archive = mirror.get(entry)
        prefix = re.sub(r"_((?:19|20)\d{2}(?:0[1-9]|1[0-2])?)$", "", Path(archive).stem)
        for member in members(archive, table):
            header = read_header(archive, member)
            best = None
            if not keep_all_versions and find_column(header, *VERSION_COLUMNS):
                best = best_versions(archive, member, header, wanted)
            for row in rows_of(archive, member):
                if keep_row(row, header, wanted, best, ordem_value):
                    yield row


def fetch(
    dataset: str,
    start: str | None = None,
    end: str | None = None,
    company=None,
    table: str | None = None,
    ordem: str = "ultimo",
    keep_all_versions: bool = False,
    cache_dir_path: str | Path | None = None,
):
    """Fetch a dataset as a DataFrame (one table) or dict of DataFrames.

    ``table`` filters ZIP members by substring (e.g. ``DRE_con``). Without it,
    every CSV in the matching archives is returned, keyed by stable table name.
    """
    start = _normalize_period(start)
    end = _normalize_period(end)
    if ordem not in ORDEM_CHOICES and ordem != "all":
        raise ValueError("ordem must be 'ultimo', 'penultimo', or 'all'")

    cache = cache_dir(cache_dir_path)
    catalog = load_catalog(cache)
    ds = resolve_dataset(catalog, dataset)
    _require_window(ds["path"], start, end)
    files = selected_files(ds, start, end)
    if not files:
        raise CVMEmptyResponseError(f"{ds['path']} has no files for the requested period")

    wanted = _wanted_companies(company)
    ordem_value = None if ordem == "all" else ORDEM_CHOICES[ordem]
    mirror = Mirror(cache / "mirror")
    ingested_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    archives: list[tuple[dict, Path, str]] = []
    headers: dict[str, list[str]] = {}
    canonical: dict[str, dict[str, str]] = {}
    layout: dict[str, dict[str, list[str]]] = {}
    for entry in files:
        archive = mirror.get(entry)
        prefix = re.sub(r"_((?:19|20)\d{2}(?:0[1-9]|1[0-2])?)$", "", Path(archive).stem)
        archives.append((entry, archive, prefix))
        for member in members(archive, table):
            key = table_key(member, prefix)
            header = read_header(archive, member)
            layout.setdefault(key, {})[member] = header
            known = headers.setdefault(key, [])
            spelling = canonical.setdefault(key, {})
            for column in header:
                folded = norm(column)
                if folded not in spelling:
                    spelling[folded] = column
                    known.append(column)
    if not headers:
        raise CVMEmptyResponseError(
            f"no CSV member matched table={table!r}" if table else "no CSV members in archive"
        )

    buckets: dict[str, list[dict]] = {key: [] for key in headers}
    for entry, archive, prefix in archives:
        for member in members(archive, table):
            key = table_key(member, prefix)
            header = layout[key][member]
            spelling = canonical[key]
            best = None
            if not keep_all_versions and find_column(header, *VERSION_COLUMNS):
                best = best_versions(archive, member, header, wanted)
            for row in rows_of(archive, member):
                if keep_row(row, header, wanted, best, ordem_value):
                    buckets[key].append(
                        {spelling[norm(k)]: v for k, v in row.items() if norm(k) in spelling}
                    )

    frames: dict[str, pd.DataFrame] = {}
    for key, rows in buckets.items():
        if not rows:
            continue
        frame = pd.DataFrame(rows, columns=headers[key])
        frames[key] = _stamp(
            frame, dataset=ds["path"], table=key, files=files, ingested_at=ingested_at,
        )

    if not frames:
        raise CVMEmptyResponseError(
            f"no rows matched dataset={ds['path']!r} table={table!r} company={company!r}"
        )
    if table is not None and len(frames) == 1:
        return next(iter(frames.values()))
    return frames


def fetch_itr(**kwargs):
    return fetch("ITR", **kwargs)


def fetch_dfp(**kwargs):
    return fetch("DFP", **kwargs)


def fetch_inf_diario(**kwargs):
    return fetch("INF_DIARIO", **kwargs)


def fetch_cda(**kwargs):
    return fetch("CDA", **kwargs)


def fetch_cadastro(**kwargs):
    return fetch("CAD", **kwargs)
