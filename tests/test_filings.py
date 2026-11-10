"""RAD/ENET listing parse, HTML-shell rejection, slug collision."""

from unittest.mock import MagicMock

import pandas as pd
import pytest

from cvmbr_data.exceptions import CVMEmptyResponseError, CVMPortalError
from cvmbr_data.filings import (
    assign_stem,
    download_filings,
    format_enet_date,
    list_filings,
    parse_enet_dados,
    payload_ext,
)


def _line(
    *,
    status="Ativo",
    category="Fato Relevante",
    subject="aumento de capital",
    seq="1",
    ver="1",
    prot="1282685",
    desc="IPE",
):
    action = f"OpenDownloadDocumentos('{seq}','{ver}','{prot}','{desc}')"
    fields = [""] * 12
    fields[2] = category
    fields[3] = "Fato Relevante"
    fields[4] = ""
    fields[5] = "31/03/2026"
    fields[6] = "01/04/2026"
    fields[7] = status
    fields[9] = "EN"
    fields[10] = action
    fields[11] = subject
    return "$&".join(fields)


class TestParse:
    def test_keeps_ativo_drops_canceled(self):
        raw = "&*".join([
            _line(prot="1", status="Ativo", subject="um"),
            _line(prot="2", status="Inativo", subject="dois"),
            _line(prot="3", status="Cancelado", subject="tres"),
        ])
        rows = parse_enet_dados(raw, "15423")
        assert len(rows) == 1
        assert rows[0]["Protocolo_Entrega"] == "1"
        assert rows[0]["Assunto"] == "um"
        assert "frmDownloadDocumento.aspx" in rows[0]["Link_Download"]

    def test_payload_ext(self):
        assert payload_ext(b"%PDF-1.4 rest") == ".pdf"
        assert payload_ext(b"PK\x03\x04zip") == ".zip"
        assert payload_ext(b"<!DOCTYPE html><html>") == ""
        assert payload_ext(b"<html>shell</html>") == ""
        assert payload_ext("a;b;c\n1;2;3\n".encode()) == ".csv"
        assert payload_ext(b"plain text body") == ".txt"

    def test_slug_collision_uses_protocol(self, tmp_path):
        used = set()
        row = {
            "Categoria": "Fato Relevante",
            "Tipo": "",
            "Especie": "",
            "Assunto": "aumento de capital",
            "Data_Referencia": "2026-03-31",
            "Data_Entrega": "2026-04-01",
            "Protocolo_Entrega": "99",
        }
        first = assign_stem(row, tmp_path, used)
        second = assign_stem({**row, "Protocolo_Entrega": "100"}, tmp_path, used)
        assert first != second
        assert "p100" in second

    def test_format_enet_date_dual(self):
        assert format_enet_date("2026-01-15") == "15/01/2026"
        assert format_enet_date("15/01/2026") == "15/01/2026"

    def test_format_enet_date_rejects_bad(self):
        with pytest.raises(ValueError):
            format_enet_date("2026/01/15")


class TestListFilings:
    def test_list_filings_parses_json(self):
        session = MagicMock()
        response = MagicMock()
        response.json.return_value = {
            "d": {"temErro": False, "dados": _line(prot="55", subject="fato")}
        }
        session.post.return_value = response
        frame = list_filings(15423, "2026-01-01", "2026-08-20", session=session)
        assert isinstance(frame, pd.DataFrame)
        assert frame.iloc[0]["Protocolo_Entrega"] == "55"
        session.post.assert_called_once()

    def test_list_filings_portal_error(self):
        session = MagicMock()
        response = MagicMock()
        response.json.return_value = {"d": {"temErro": True, "msgErro": "boom"}}
        session.post.return_value = response
        with pytest.raises(CVMPortalError, match="boom"):
            list_filings(15423, "01/01/2026", "20/08/2026", session=session)

    def test_list_filings_empty(self):
        session = MagicMock()
        response = MagicMock()
        response.json.return_value = {"d": {"temErro": False, "dados": ""}}
        session.post.return_value = response
        with pytest.raises(CVMEmptyResponseError):
            list_filings(15423, "2026-01-01", "2026-01-02", session=session)

    def test_inverted_range(self):
        with pytest.raises(ValueError):
            list_filings(15423, "2026-08-20", "2026-01-01", session=MagicMock())


class TestDownload:
    def test_rejects_html_shell(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cvmbr_data.filings.time.sleep", lambda s: None)

        def fake_get(url, **kwargs):
            response = MagicMock()
            response.raise_for_status.return_value = None
            response.status_code = 200
            if "frmConsultaExternaCVM" in url:
                response.content = b"ok"
            else:
                response.content = b"<html>empty shell</html>"
            return response

        session = MagicMock()
        session.get.side_effect = fake_get
        docs = parse_enet_dados(_line(prot="1", subject="fato"), "15423")
        frame = download_filings(docs, tmp_path, codigo_cvm=15423, session=session)
        assert frame.iloc[0]["Status"] == "failed"
        assert "unexpected payload" in frame.iloc[0]["Erro"]
        assert frame.attrs["manifest"]

    def test_writes_pdf_and_manifest(self, tmp_path, monkeypatch):
        monkeypatch.setattr("cvmbr_data.filings.time.sleep", lambda s: None)

        def fake_get(url, **kwargs):
            response = MagicMock()
            response.raise_for_status.return_value = None
            response.status_code = 200
            if "frmConsultaExternaCVM" in url:
                response.content = b"ok"
            else:
                response.content = b"%PDF-1.4 filing"
            return response

        session = MagicMock()
        session.get.side_effect = fake_get
        docs = parse_enet_dados(_line(prot="1", subject="fato"), "15423")
        frame = download_filings(
            docs, tmp_path, codigo_cvm=15423,
            date_from="2026-01-01", date_to="2026-08-20", session=session,
        )
        assert frame.iloc[0]["Status"] == "downloaded"
        written = list(tmp_path.glob("*.pdf"))
        assert written
        assert (tmp_path / "manifest-cvm-20260101-20260820.csv").exists()
