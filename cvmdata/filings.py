"""Live RAD/ENET filings: list active documents and download them."""

from __future__ import annotations

import csv
import html
import json
import re
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path

import pandas as pd
import requests

from .constants import (
    DATE_FORMAT,
    ENET_DOWNLOAD,
    ENET_LIST,
    ENET_PAGE,
    ISO_DATE_FORMAT,
    RAD_DOWNLOAD_PAUSE,
)
from .exceptions import CVMEmptyResponseError, CVMPortalError
from .http import enet_user_agent

ABBR = {
    "Fato Relevante": "FR",
    "Comunicado ao Mercado": "COM",
    "Aviso aos Acionistas": "AVISO",
    "Assembleia": "AG",
    "Reunião da Administração": "RCA",
    "Informações de Companhias em Recuperação Judicial ou Extrajudicial": "RJ",
    "Dados Econômico-Financeiros": "DF",
    "Valores Mobiliários Negociados e Detidos": "ART11",
    "FRE - Formulário de Referência": "FRE",
    "FCA - Formulário Cadastral": "FCA",
    "DFP - Demonstrações Financeiras Padronizadas": "DFP",
    "ITR - Informações Trimestrais": "ITR",
}

MANIFEST_FIELDS = [
    "Arquivo", "Status", "Codigo_CVM", "Data_Referencia", "Categoria", "Tipo",
    "Especie", "Assunto", "Data_Entrega", "Tipo_Apresentacao", "Protocolo_Entrega",
    "Versao", "Link_Download", "Erro",
]


def format_enet_date(value) -> str:
    """Accept YYYY-MM-DD, DD/MM/YYYY, or date/datetime; return DD/MM/YYYY."""
    if value is None:
        raise ValueError("date is required")
    if isinstance(value, datetime):
        return value.strftime(DATE_FORMAT)
    if isinstance(value, date):
        return value.strftime(DATE_FORMAT)
    if isinstance(value, str):
        for fmt in (ISO_DATE_FORMAT, DATE_FORMAT):
            try:
                return datetime.strptime(value, fmt).strftime(DATE_FORMAT)
            except ValueError:
                continue
        raise ValueError(f"Invalid date format: {value}. Use YYYY-MM-DD or DD/MM/YYYY.")
    raise TypeError(f"Expected str or date, got {type(value).__name__}")


def clean_text(value: str) -> str:
    value = (value or "").replace("º", "o").replace("ª", "a").replace("&gt;", "").replace(">", "")
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii").lower()
    value = re.sub(r"[^a-z0-9]+", "-", value).strip("-")
    return re.sub(r"-+", "-", value)


def strip_html(value: str) -> str:
    return re.sub(r"<.*?>", "", html.unescape(value or "")).strip()


def extract_date(value: str) -> str:
    text = strip_html(value)
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    return ""


def extract_ref(value: str) -> str:
    text = strip_html(value)
    match = re.search(r"(\d{2})/(\d{2})/(\d{4})", text)
    if match:
        return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"
    match = re.search(r"(\d{2})/(\d{4})", text)
    if match:
        return f"{match.group(2)}-{match.group(1)}-01"
    match = re.search(r"(\d{4})", text)
    return match.group(1) if match else ""


def download_params(action_html: str):
    match = re.search(
        r"OpenDownloadDocumentos\('([^']+)','([^']+)','([^']*)','([^']*)'\)",
        action_html or "",
    )
    return match.groups() if match else None


def topic_for(category: str, doc_type: str, species_subject: str, subject: str, ref: str) -> str:
    if subject:
        if category == "Assembleia" and doc_type:
            return f"{doc_type} {subject}"
        return subject
    if category == "Assembleia":
        return " ".join(x for x in [doc_type, species_subject] if x)
    if category == "Reunião da Administração":
        return species_subject or doc_type
    if category.startswith("Informações de Companhias"):
        return species_subject or doc_type
    if category.startswith("Valores Mobiliários"):
        return "posicao-consolidada-art11-ref-" + ref[:7]
    if category == "Dados Econômico-Financeiros":
        return "demonstracoes-financeiras-anuais-" + (ref[:4] or "")
    if category.startswith("FRE"):
        return "formulario-referencia-" + ref
    if category.startswith("FCA"):
        return "formulario-cadastral-" + ref
    if category.startswith("DFP"):
        return "demonstracoes-financeiras-padronizadas-" + ref
    return subject or species_subject or doc_type or category


def parse_enet_dados(raw: str, codigo_cvm: str) -> list[dict]:
    rows = []
    for line in (raw or "").split("&*"):
        if not line.strip():
            continue
        fields = line.split("$&")
        if len(fields) < 11 or strip_html(fields[7]) != "Ativo":
            continue
        params = download_params(fields[10])
        if not params:
            continue
        seq, ver, prot, desc = params
        category = strip_html(fields[2])
        doc_type = strip_html(fields[3]).strip(" -")
        species_subject = strip_html(fields[4]).strip(" -")
        subject = strip_html(fields[11]) if len(fields) > 11 else ""
        ref = extract_ref(fields[5])
        delivery = extract_date(fields[6])
        rows.append({
            "Arquivo": "",
            "Status": "pending",
            "Erro": "",
            "Codigo_CVM": str(codigo_cvm),
            "Data_Referencia": ref,
            "Categoria": category,
            "Tipo": doc_type,
            "Especie": species_subject,
            "Assunto": subject,
            "Data_Entrega": delivery,
            "Tipo_Apresentacao": strip_html(fields[9]),
            "Protocolo_Entrega": prot,
            "Versao": ver,
            "Link_Download": ENET_DOWNLOAD.format(desc=desc, prot=prot, seq=seq, ver=ver),
        })
    return rows


def assign_stem(row: dict, out_dir: Path, used_stems: set[str]) -> str:
    abbr = ABBR.get(row["Categoria"], clean_text(row["Categoria"]).upper()[:8] or "DOC")
    slug = clean_text(topic_for(
        row["Categoria"], row["Tipo"], row["Especie"], row["Assunto"], row["Data_Referencia"],
    ))[:90]
    stem = re.sub(r"-+", "-", f"{row['Data_Entrega']}-{abbr}-{slug}".strip("-"))
    if stem in used_stems or list(out_dir.glob(stem + ".*")):
        stem = base = f"{stem}-p{row['Protocolo_Entrega']}"
        n = 2
        while stem in used_stems or list(out_dir.glob(stem + ".*")):
            stem = f"{base}-{n}"
            n += 1
    used_stems.add(stem)
    return stem


def payload_ext(data: bytes) -> str:
    """Extension for a downloaded payload, or "" when it is not a real document."""
    if data[:4] == b"%PDF":
        return ".pdf"
    if data[:2] == b"PK":
        return ".zip"
    head = data[:1000].lower()
    if b"<html" in head or b"<!doctype html" in head:
        return ""
    try:
        first_line = data.decode("utf-8").splitlines()[0]
    except (UnicodeDecodeError, IndexError):
        return ""
    return ".csv" if first_line.count(";") >= 2 else ".txt"


def _session() -> requests.Session:
    session = requests.Session()
    session.headers.update({
        "User-Agent": enet_user_agent(),
        "Referer": "https://www.rad.cvm.gov.br/ENETWeb/frmConsultaExternaCVM.aspx",
    })
    return session


def prime_session(session: requests.Session, codigo_cvm: str) -> None:
    """Seed the ASP.NET session cookie by visiting the consulta page.

    Structured exports (ITR/DFP/FRE/FCA) are served only to a session that
    visited it; without the cookie ENET answers 200 text/html with an empty shell.
    """
    url = ENET_PAGE.format(codigo=codigo_cvm)
    response = session.get(url, timeout=60)
    response.raise_for_status()


def list_filings(
    codigo_cvm,
    date_from,
    date_to,
    all_docs: bool = True,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """List active RAD/ENET documents for one companhia aberta."""
    codigo = str(codigo_cvm).lstrip("0") or "0"
    padded = str(codigo_cvm).zfill(6)
    start = format_enet_date(date_from)
    end = format_enet_date(date_to)
    start_dt = datetime.strptime(start, DATE_FORMAT)
    end_dt = datetime.strptime(end, DATE_FORMAT)
    if end_dt < start_dt:
        raise ValueError(f"date_to ({end}) is before date_from ({start})")

    category = "EST_-1,IPE_-1_-1_-1" if all_docs else "IPE_-1_-1_-1"
    payload = {
        "dataDe": start,
        "dataAte": end,
        "empresa": f",{padded}",
        "setorAtividade": "-1",
        "categoriaEmissor": "-1",
        "situacaoEmissor": "-1",
        "tipoParticipante": "-1",
        "dataReferencia": "",
        "categoria": category,
        "periodo": "2",
        "horaIni": "",
        "horaFim": "",
        "palavraChave": "",
        "ultimaDtRef": "false",
        "tipoEmpresa": "0",
        "token": "",
        "versaoCaptcha": "",
    }
    own_session = session is None
    sess = session or _session()
    try:
        response = sess.post(
            ENET_LIST,
            json=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": ENET_PAGE.format(codigo=codigo),
            },
            timeout=60,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, json.JSONDecodeError, ValueError) as exc:
        raise CVMPortalError(f"RAD/ENET ListarDocumentos failed: {exc}") from exc
    finally:
        if own_session:
            sess.close()

    retorno = data.get("d") if isinstance(data, dict) else None
    if not isinstance(retorno, dict):
        raise CVMPortalError("RAD/ENET returned an unexpected JSON shape")
    if retorno.get("temErro"):
        raise CVMPortalError(retorno.get("msgErro") or "RAD/ENET returned an error")
    rows = parse_enet_dados(retorno.get("dados") or "", codigo)
    if not rows:
        raise CVMEmptyResponseError(
            f"no active filings for CVM {codigo} between {start} and {end}"
        )
    return pd.DataFrame(rows)


def _rows_from(docs) -> list[dict]:
    if isinstance(docs, pd.DataFrame):
        return docs.to_dict(orient="records")
    return [dict(row) for row in docs]


def read_manifest(manifest: Path) -> dict[tuple[str, str], dict]:
    if not manifest.exists():
        return {}
    with manifest.open(encoding="utf-8", newline="") as handle:
        return {
            (r.get("Protocolo_Entrega", ""), r.get("Versao", "")): r
            for r in csv.DictReader(handle, delimiter=";")
        }


def write_manifest(manifest: Path, rows: list[dict]) -> int:
    merged = read_manifest(manifest)
    for row in rows:
        merged[(str(row["Protocolo_Entrega"]), str(row["Versao"]))] = row
    ordered = sorted(
        merged.values(),
        key=lambda r: (r.get("Data_Entrega", ""), r.get("Protocolo_Entrega", "")),
    )
    with manifest.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=MANIFEST_FIELDS, delimiter=";")
        writer.writeheader()
        writer.writerows({k: r.get(k, "") for k in MANIFEST_FIELDS} for r in ordered)
    return len(ordered)


def _download_one(session: requests.Session, row: dict, stem_path: Path) -> None:
    tmp = stem_path.parent / (stem_path.name + ".download")
    response = session.get(row["Link_Download"], timeout=240)
    if response.status_code >= 400:
        row["Arquivo"] = stem_path.name
        row["Status"] = "failed"
        row["Erro"] = f"HTTP {response.status_code}"
        return
    data = response.content or b""
    if not data:
        row["Arquivo"] = stem_path.name
        row["Status"] = "failed"
        row["Erro"] = "empty payload"
        return
    ext = payload_ext(data)
    if not ext:
        row["Arquivo"] = stem_path.name
        row["Status"] = "failed"
        row["Erro"] = f"unexpected payload, not PDF/ZIP/text ({len(data)} bytes)"
        return
    out = stem_path.parent / f"{stem_path.name}{ext}"
    tmp.write_bytes(data)
    tmp.replace(out)
    row["Arquivo"] = out.name
    row["Status"] = "downloaded"
    row["Erro"] = ""


def download_filings(
    docs,
    out: str | Path,
    codigo_cvm=None,
    date_from=None,
    date_to=None,
    session: requests.Session | None = None,
) -> pd.DataFrame:
    """Download listed filings into ``out`` and merge a protocol+version manifest."""
    rows = _rows_from(docs)
    if not rows:
        raise CVMEmptyResponseError("no filings to download")
    out_dir = Path(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    codigo = str(codigo_cvm or rows[0].get("Codigo_CVM") or "").lstrip("0") or "0"

    if date_from and date_to:
        window_from = datetime.strptime(format_enet_date(date_from), DATE_FORMAT)
        window_to = datetime.strptime(format_enet_date(date_to), DATE_FORMAT)
        window = f"{window_from:%Y%m%d}-{window_to:%Y%m%d}"
    else:
        deliveries = [r.get("Data_Entrega") or "" for r in rows]
        start = min(deliveries) if deliveries else ""
        end = max(deliveries) if deliveries else ""
        window = f"{start.replace('-', '')}-{end.replace('-', '')}" if start and end else "filings"
    manifest = out_dir / f"manifest-cvm-{window}.csv"
    known = read_manifest(manifest)

    own_session = session is None
    sess = session or _session()
    try:
        prime_session(sess, codigo)
        used: set[str] = set()
        for row in rows:
            prev = known.get((str(row["Protocolo_Entrega"]), str(row["Versao"])))
            if prev and prev.get("Status") in ("downloaded", "cached") and (out_dir / prev["Arquivo"]).exists():
                row["Arquivo"] = prev["Arquivo"]
                row["Status"] = "cached"
                row["Erro"] = ""
                used.add(Path(prev["Arquivo"]).stem)
                continue
            stem = assign_stem(row, out_dir, used)
            _download_one(sess, row, out_dir / stem)
            time.sleep(RAD_DOWNLOAD_PAUSE)

        retried = [r for r in rows if r["Status"] == "failed"]
        if retried:
            prime_session(sess, codigo)
        for row in retried:
            time.sleep(2)
            stem = Path(row["Arquivo"]).stem or assign_stem(row, out_dir, used)
            _download_one(sess, row, out_dir / stem)
    finally:
        if own_session:
            sess.close()

    write_manifest(manifest, rows)
    frame = pd.DataFrame(rows)
    frame.attrs["manifest"] = str(manifest)
    return frame
