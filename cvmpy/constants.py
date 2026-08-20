"""Shared constants for the CVM open-data portal and RAD/ENET."""

from __future__ import annotations

PORTAL = "https://dados.cvm.gov.br/"
DATA_ROOT = PORTAL + "dados/"
CKAN_PACKAGES = PORTAL + "api/3/action/current_package_list_with_resources?limit=500"
CKAN_GROUPS = PORTAL + "api/3/action/group_list?all_fields=true"

ENET_PAGE = (
    "https://www.rad.cvm.gov.br/ENETWeb/frmConsultaExternaCVM.aspx?codigoCVM={codigo}"
)
ENET_LIST = (
    "https://www.rad.cvm.gov.br/ENETWeb/frmConsultaExternaCVM.aspx/ListarDocumentos"
)
ENET_DOWNLOAD = (
    "https://www.rad.cvm.gov.br/ENET/frmDownloadDocumento.aspx"
    "?Tela=ext&descTipo={desc}&CodigoInstituicao=1"
    "&numProtocolo={prot}&numSequencia={seq}&numVersao={ver}"
)

SOURCE_ENCODING = "latin-1"
DELIMITER = ";"
DATE_FORMAT = "%d/%m/%Y"
ISO_DATE_FORMAT = "%Y-%m-%d"

MAX_DEPTH = 5
CRAWL_WORKERS = 2
HTTP_TIMEOUT = 90
DOWNLOAD_TIMEOUT = 600
HTTP_RETRIES = 3
STREAM_CHUNK = 256 * 1024
RAD_DOWNLOAD_PAUSE = 0.1
CIRCUIT_FAILURES = 5
MAX_RETRY_DELAY = 60.0
PARSER_VERSION = "cvm-csv-latin1-1"

CACHE_ENV = "CVMPY_CACHE"
CACHE_NAME = "cvmpy"

# fetch() materializes tables in memory. These datasets are too large to pull
# without a period window.
UNBOUNDED_PATHS = frozenset({
    "FI/DOC/INF_DIARIO",
    "FI/DOC/CDA",
})

REPO_URL = "https://github.com/rteoo/cvmpy"
