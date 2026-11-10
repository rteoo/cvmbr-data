"""CVM CSV hygiene: latin-1, company keys, ORDEM_EXERC, highest VERSAO."""

from __future__ import annotations

import csv
import io
import re
import sys
import zipfile
from pathlib import Path

from .constants import DELIMITER, SOURCE_ENCODING

csv.field_size_limit(min(sys.maxsize, 2 ** 31 - 1))

CODE_COLUMNS = {"CD_CVM", "CODIGO_CVM", "CD_CVM_FUNDO"}
VERSION_COLUMNS = {"VERSAO"}
REFERENCE_COLUMNS = {"DT_REFER", "DATA_REFERENCIA", "DT_COMPTC"}
ORDEM_COLUMN = "ORDEM_EXERC"
ORDEM_CHOICES = {"ultimo": "ÚLTIMO", "penultimo": "PENÚLTIMO"}


def norm(name: str) -> str:
    """Case-folded column name, for matching only.

    Output keeps CVM's original spelling so results still join against META/.
    """
    return name.strip().lstrip("\ufeff").upper()


def find_column(header: list[str], *names: str) -> str | None:
    wanted = {n.upper() for n in names}
    return next((c for c in header if norm(c) in wanted), None)


def digits(value: str) -> str:
    return re.sub(r"\D", "", value or "")


def company_key(value: str) -> str:
    """Normalize so 021610, 21610 and a punctuated CNPJ all match."""
    only = digits(value)
    return only.lstrip("0") or only


def members(archive: Path, table: str | None = None) -> list[str]:
    with zipfile.ZipFile(archive) as zipped:
        names = [n for n in zipped.namelist() if n.lower().endswith(".csv")]
    if table:
        needle = table.lower()
        names = [n for n in names if needle in n.lower()]
    return sorted(names)


def table_key(member: str, dataset_prefix: str) -> str:
    """Stable table name across periods: itr_cia_aberta_DRE_con_2026.csv -> DRE_con."""
    stem = Path(member).stem
    stem = re.sub(r"_((?:19|20)\d{2}(?:0[1-9]|1[0-2])?)$", "", stem)
    if dataset_prefix and stem.lower().startswith(dataset_prefix.lower()):
        stem = stem[len(dataset_prefix):].strip("_")
    return stem or "documentos"


def read_header(archive: Path, member: str) -> list[str]:
    with zipfile.ZipFile(archive) as zipped, zipped.open(member) as raw:
        line = raw.readline().decode(SOURCE_ENCODING)
    return [c.strip().lstrip("\ufeff") for c in next(csv.reader([line], delimiter=DELIMITER))]


def rows_of(archive: Path, member: str):
    with zipfile.ZipFile(archive) as zipped, zipped.open(member) as raw:
        stream = io.TextIOWrapper(raw, encoding=SOURCE_ENCODING, newline="")
        reader = csv.reader(stream, delimiter=DELIMITER)
        header = [c.strip().lstrip("\ufeff") for c in next(reader)]
        for row in reader:
            if len(row) < len(header):
                row = row + [""] * (len(header) - len(row))
            yield dict(zip(header, row))


def matches_company(row: dict, wanted: set[str]) -> bool:
    for column, value in row.items():
        key = norm(column)
        if "CNPJ" in key or key in CODE_COLUMNS:
            if company_key(value) in wanted:
                return True
    return False


def identity(row: dict, header: list[str]) -> tuple:
    keys = [
        c for c in header
        if "CNPJ" in norm(c) or norm(c) in CODE_COLUMNS or norm(c) in REFERENCE_COLUMNS
    ]
    return tuple(row.get(c, "") for c in keys)


def best_versions(
    archive: Path,
    member: str,
    header: list[str],
    wanted: set[str] | None,
) -> dict[tuple, int]:
    """Highest VERSAO per filed document, so a restatement replaces its original."""
    best: dict[tuple, int] = {}
    version_col = find_column(header, *VERSION_COLUMNS)
    for row in rows_of(archive, member):
        if wanted and not matches_company(row, wanted):
            continue
        raw = row.get(version_col, "") if version_col else ""
        version = int(raw) if raw.isdigit() else 0
        key = identity(row, header)
        if version > best.get(key, -1):
            best[key] = version
    return best


def keep_row(
    row: dict,
    header: list[str],
    wanted: set[str] | None,
    best: dict[tuple, int] | None,
    ordem: str | None,
) -> bool:
    if wanted and not matches_company(row, wanted):
        return False
    if ordem:
        ordem_col = find_column(header, ORDEM_COLUMN)
        if ordem_col and norm(row.get(ordem_col, "")) != norm(ordem):
            return False
    if best is not None:
        version_col = find_column(header, *VERSION_COLUMNS)
        raw = row.get(version_col, "") if version_col else ""
        version = int(raw) if raw.isdigit() else 0
        if best.get(identity(row, header), -1) != version:
            return False
    return True
