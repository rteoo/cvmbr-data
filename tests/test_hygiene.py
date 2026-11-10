"""CVM CSV hygiene: encoding, company keys, ORDEM_EXERC, VERSAO."""

import io
import zipfile
from pathlib import Path

from cvmbr_data.hygiene import (
    best_versions,
    company_key,
    keep_row,
    members,
    read_header,
    rows_of,
    table_key,
)


def _zip_bytes(members_map: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zipped:
        for name, text in members_map.items():
            zipped.writestr(name, text.encode("latin-1"))
    return buf.getvalue()


def _write_zip(path: Path, members_map: dict[str, str]) -> Path:
    path.write_bytes(_zip_bytes(members_map))
    return path


class TestKeys:
    def test_company_key_strips_punctuation_and_zeros(self):
        assert company_key("015423") == company_key("15423")
        assert company_key("28.152.872/0001-77") == "28152872000177"

    def test_table_key_strips_dataset_prefix_and_year(self):
        assert table_key("itr_cia_aberta_DRE_con_2024.csv", "itr_cia_aberta") == "DRE_con"


class TestFilters:
    def test_latin1_accents_round_trip(self, tmp_path):
        archive = _write_zip(tmp_path / "sample.zip", {
            "itr_cia_aberta_DRE_con_2024.csv": (
                "CNPJ_CIA;CD_CVM;DT_REFER;VERSAO;ORDEM_EXERC;DS_CONTA\n"
                "12.345.678/0001-90;015423;2024-03-31;1;ÚLTIMO;Receita líquida\n"
            ),
        })
        header = read_header(archive, "itr_cia_aberta_DRE_con_2024.csv")
        rows = list(rows_of(archive, "itr_cia_aberta_DRE_con_2024.csv"))
        assert "DS_CONTA" in header
        assert rows[0]["DS_CONTA"] == "Receita líquida"
        assert rows[0]["ORDEM_EXERC"] == "ÚLTIMO"

    def test_ordem_ultimo_drops_penultimo(self, tmp_path):
        archive = _write_zip(tmp_path / "itr.zip", {
            "itr_cia_aberta_DRE_con_2024.csv": (
                "CNPJ_CIA;CD_CVM;DT_REFER;VERSAO;ORDEM_EXERC;VL_CONTA\n"
                "12.345.678/0001-90;015423;2024-03-31;1;ÚLTIMO;100\n"
                "12.345.678/0001-90;015423;2024-03-31;1;PENÚLTIMO;90\n"
            ),
        })
        member = "itr_cia_aberta_DRE_con_2024.csv"
        header = read_header(archive, member)
        kept = [
            row for row in rows_of(archive, member)
            if keep_row(row, header, None, None, "ÚLTIMO")
        ]
        assert [r["VL_CONTA"] for r in kept] == ["100"]

    def test_versao_keeps_highest_on_vlmo_shape(self, tmp_path):
        archive = _write_zip(tmp_path / "vlmo.zip", {
            "vlmo_cia_aberta_2025.csv": (
                "CNPJ_Companhia;CD_CVM;DT_REFER;VERSAO;VL_ACAO\n"
                "12.345.678/0001-90;015423;2025-01-31;1;10\n"
                "12.345.678/0001-90;015423;2025-01-31;2;12\n"
                "98.765.432/0001-10;000099;2025-01-31;1;5\n"
            ),
        })
        member = "vlmo_cia_aberta_2025.csv"
        header = read_header(archive, member)
        best = best_versions(archive, member, header, None)
        kept = [
            row for row in rows_of(archive, member)
            if keep_row(row, header, None, best, None)
        ]
        values = {(r["CD_CVM"], r["VERSAO"], r["VL_ACAO"]) for r in kept}
        assert values == {("015423", "2", "12"), ("000099", "1", "5")}

    def test_company_filter_matches_padded_cvm_code(self, tmp_path):
        archive = _write_zip(tmp_path / "itr.zip", {
            "itr_cia_aberta_DRE_con_2024.csv": (
                "CNPJ_CIA;CD_CVM;DT_REFER;VERSAO;ORDEM_EXERC;VL_CONTA\n"
                "12.345.678/0001-90;015423;2024-03-31;1;ÚLTIMO;100\n"
                "98.765.432/0001-10;000099;2024-03-31;1;ÚLTIMO;1\n"
            ),
        })
        member = members(archive)[0]
        header = read_header(archive, member)
        wanted = {company_key("15423")}
        kept = [
            row for row in rows_of(archive, member)
            if keep_row(row, header, wanted, None, "ÚLTIMO")
        ]
        assert len(kept) == 1
        assert kept[0]["CD_CVM"] == "015423"
