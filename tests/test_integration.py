"""Live CVM portal tests — opt-in, excluded from CI."""

from datetime import date

import pandas as pd
import pytest

import cvmbr_data

pytestmark = pytest.mark.integration


def test_refresh_catalog_sees_itr_and_inf_diario_hist(tmp_path):
    catalog = cvmbr_data.refresh_catalog(tmp_path)
    paths = {ds["path"] for ds in catalog["datasets"]}
    assert "CIA_ABERTA/DOC/ITR" in paths
    assert "FI/DOC/INF_DIARIO" in paths
    inf = next(ds for ds in catalog["datasets"] if ds["path"] == "FI/DOC/INF_DIARIO")
    assert any(f.get("archived") for f in inf["files"]), "HIST/ archives missing from INF_DIARIO"


def test_fetch_itr_dre(tmp_path):
    cvmbr_data.refresh_catalog(tmp_path)
    year = str(date.today().year)
    frame = cvmbr_data.fetch(
        "ITR",
        start=year,
        company="15423",
        table="DRE_con",
        cache_dir_path=tmp_path,
    )
    assert isinstance(frame, pd.DataFrame)
    assert len(frame) > 0
    assert frame.attrs["source"] == "CIA_ABERTA/DOC/ITR"


def test_list_filings_short_window():
    today = date.today()
    start = date(today.year, 1, 1)
    frame = cvmbr_data.list_filings(15423, start, today, all_docs=False)
    assert isinstance(frame, pd.DataFrame)
    assert len(frame) > 0
    assert "Protocolo_Entrega" in frame.columns
