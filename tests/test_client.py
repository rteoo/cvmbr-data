"""fetch() DataFrames, hygiene defaults, unbounded-period guard."""

import io
import json
import zipfile
from pathlib import Path

import pandas as pd
import pytest

from cvmbr_data.catalog import catalog_paths
from cvmbr_data.client import fetch, fetch_itr, iter_archive_rows, iter_rows, list_tables
from cvmbr_data.exceptions import CVMEmptyResponseError, CVMError


def _zip(members_map: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zipped:
        for name, text in members_map.items():
            zipped.writestr(name, text.encode("latin-1"))
    return buf.getvalue()


def _seed(cache: Path, *, path: str, filename: str, period: str, members_map: dict[str, str], area: str = "CIA_ABERTA"):
    url = f"https://dados.cvm.gov.br/dados/{path}/DADOS/{filename}"
    catalog = {
        "generated_at": "2026-08-20T12:00:00+00:00",
        "source": "https://dados.cvm.gov.br/",
        "groups": {},
        "datasets": [{
            "path": path,
            "area": area,
            "title": path,
            "files": [{
                "url": url,
                "name": filename,
                "modified": "2026-03-15 08:00",
                "size_raw": "1M",
                "bytes": 1024,
                "period": period,
                "archived": False,
            }],
            "meta": [],
        }],
        "external_packages": [],
    }
    current, _ = catalog_paths(cache)
    current.parent.mkdir(parents=True, exist_ok=True)
    current.write_text(json.dumps(catalog), encoding="utf-8")
    dest = cache / "mirror" / path / "DADOS" / filename
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(_zip(members_map))
    dest.with_suffix(dest.suffix + ".meta").write_text(
        json.dumps({"modified": "2026-03-15 08:00", "size_raw": "1M"}),
        encoding="utf-8",
    )
    return cache


ITR_CSV = (
    "CNPJ_CIA;CD_CVM;DT_REFER;VERSAO;ORDEM_EXERC;VL_CONTA\n"
    "12.345.678/0001-90;015423;2024-03-31;1;ÚLTIMO;100\n"
    "12.345.678/0001-90;015423;2024-03-31;2;ÚLTIMO;110\n"
    "12.345.678/0001-90;015423;2024-03-31;2;PENÚLTIMO;90\n"
    "98.765.432/0001-10;000099;2024-03-31;1;ÚLTIMO;5\n"
)


class TestFetch:
    def test_table_returns_dataframe_with_hygiene(self, tmp_path):
        cache = _seed(
            tmp_path,
            path="CIA_ABERTA/DOC/ITR",
            filename="itr_cia_aberta_2024.zip",
            period="2024",
            members_map={"itr_cia_aberta_DRE_con_2024.csv": ITR_CSV},
        )
        frame = fetch("ITR", start="2024", company="15423", table="DRE_con", cache_dir_path=cache)
        assert isinstance(frame, pd.DataFrame)
        assert list(frame["VL_CONTA"]) == ["110"]
        assert frame.attrs["source"] == "CIA_ABERTA/DOC/ITR"
        assert frame.attrs["table"] == "DRE_con"
        assert "ingested_at" in frame.attrs

    def test_without_table_returns_dict(self, tmp_path):
        cache = _seed(
            tmp_path,
            path="CIA_ABERTA/DOC/ITR",
            filename="itr_cia_aberta_2024.zip",
            period="2024",
            members_map={
                "itr_cia_aberta_DRE_con_2024.csv": ITR_CSV,
                "itr_cia_aberta_BPA_con_2024.csv": ITR_CSV.replace("VL_CONTA", "VL_CONTA"),
            },
        )
        result = fetch_itr(start="2024", company="15423", cache_dir_path=cache)
        assert isinstance(result, dict)
        assert "DRE_con" in result
        assert "BPA_con" in result

    def test_unbounded_inf_diario_raises(self, tmp_path):
        cache = _seed(
            tmp_path,
            path="FI/DOC/INF_DIARIO",
            filename="inf_diario_fi_202608.zip",
            period="202608",
            area="FI",
            members_map={"inf_diario_fi_202608.csv": "CNPJ_FUNDO;VL_QUOTA\n28.152.872/0001-77;1.0\n"},
        )
        with pytest.raises(CVMError, match="too large"):
            fetch("INF_DIARIO", cache_dir_path=cache)

    def test_inf_diario_with_period_ok(self, tmp_path):
        cache = _seed(
            tmp_path,
            path="FI/DOC/INF_DIARIO",
            filename="inf_diario_fi_202608.zip",
            period="202608",
            area="FI",
            members_map={"inf_diario_fi_202608.csv": "CNPJ_FUNDO;VL_QUOTA\n28.152.872/0001-77;1.0\n"},
        )
        frame = fetch("INF_DIARIO", start="202608", table="inf_diario", cache_dir_path=cache)
        assert len(frame) == 1

    def test_iter_rows_unbounded_allowed(self, tmp_path):
        cache = _seed(
            tmp_path,
            path="FI/DOC/INF_DIARIO",
            filename="inf_diario_fi_202608.zip",
            period="202608",
            area="FI",
            members_map={"inf_diario_fi_202608.csv": "CNPJ_FUNDO;VL_QUOTA\n28.152.872/0001-77;1.0\n"},
        )
        rows = list(iter_rows("INF_DIARIO", cache_dir_path=cache))
        assert len(rows) == 1

    def test_iter_archive_rows_applies_hygiene_to_csv_bytes(self):
        rows = list(iter_archive_rows(ITR_CSV.encode("latin-1"), company="15423"))
        assert len(rows) == 1
        assert rows[0]["VERSAO"] == "2"
        assert rows[0]["ORDEM_EXERC"] == "ÚLTIMO"

    def test_unknown_company_is_empty(self, tmp_path):
        cache = _seed(
            tmp_path,
            path="CIA_ABERTA/DOC/ITR",
            filename="itr_cia_aberta_2024.zip",
            period="2024",
            members_map={"itr_cia_aberta_DRE_con_2024.csv": ITR_CSV},
        )
        with pytest.raises(CVMEmptyResponseError):
            fetch("ITR", start="2024", company="999999", table="DRE_con", cache_dir_path=cache)

    def test_list_tables(self, tmp_path):
        cache = _seed(
            tmp_path,
            path="CIA_ABERTA/DOC/ITR",
            filename="itr_cia_aberta_2024.zip",
            period="2024",
            members_map={"itr_cia_aberta_DRE_con_2024.csv": ITR_CSV},
        )
        tables = list_tables("ITR", cache_dir_path=cache)
        assert tables[0]["table"] == "DRE_con"
        assert tables[0]["columns"] == 6

    def test_period_yyyy_mm_dd_normalizes(self, tmp_path):
        cache = _seed(
            tmp_path,
            path="CIA_ABERTA/DOC/ITR",
            filename="itr_cia_aberta_2024.zip",
            period="2024",
            members_map={"itr_cia_aberta_DRE_con_2024.csv": ITR_CSV},
        )
        frame = fetch("ITR", start="2024-03-01", end="2024-03-31", table="DRE_con", cache_dir_path=cache)
        assert len(frame) == 2  # two companies, ultimo + highest versao
