"""CVM open-data catalog — CKAN metadata over the /dados/ autoindex, including HIST/.

Neither side alone is enough: CKAN lists only the most recent years of each
dataset, while the autoindex has the full archive but no titles. This module
merges both into one local catalog.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from .constants import (
    CACHE_ENV,
    CACHE_NAME,
    CKAN_GROUPS,
    CKAN_PACKAGES,
    CRAWL_WORKERS,
    DATA_ROOT,
    MAX_DEPTH,
    PORTAL,
)
from .datasets import DATASETS
from .exceptions import CVMAmbiguousDatasetError, CVMCatalogError, CVMError, CVMPortalError
from .http import HttpClient, http_get

LISTING_ROW = re.compile(
    r'<a href="([^"?][^"]*)">[^<]*</a>\s+(\d{2}-\w{3}-\d{4} \d{2}:\d{2})\s+(\S+)'
)
MONTHS = {
    m: i for i, m in enumerate(
        "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(), start=1,
    )
}
SIZE_UNITS = {"K": 1024, "M": 1024 ** 2, "G": 1024 ** 3, "T": 1024 ** 4}
PERIOD = re.compile(r"_((?:19|20)\d{2}(?:0[1-9]|1[0-2])?)(?=\D|$)")


def cache_dir(override: str | Path | None = None) -> Path:
    """Local catalog/mirror root. Never inside a git repo by default."""
    if override is not None:
        return Path(override)
    env = os.environ.get(CACHE_ENV) or os.environ.get("CVMPY_CACHE")
    if env:
        return Path(env)
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local")
    else:
        base = os.environ.get("XDG_CACHE_HOME") or (Path.home() / ".cache")
    return Path(base) / CACHE_NAME


def catalog_paths(cache: Path) -> tuple[Path, Path]:
    return cache / "catalog.json", cache / "catalog.prev.json"


def load_catalog(cache: str | Path | None = None) -> dict:
    current, _ = catalog_paths(cache_dir(cache))
    if not current.exists():
        raise CVMCatalogError(
            f"no catalog at {current} — call refresh_catalog() first"
        )
    return json.loads(current.read_text(encoding="utf-8"))


def parse_listing_date(value: str) -> str:
    day, month, rest = value.split("-", 2)
    year, clock = rest.split(" ", 1)
    if month not in MONTHS:
        raise CVMPortalError(f"unknown month {month!r} in listing date {value!r}")
    return f"{year}-{MONTHS[month]:02d}-{day} {clock}"


def parse_size(token: str) -> int:
    """Approximate byte count for an autoindex size token.

    ceiling: the autoindex rounds sizes to three significant digits, so these
    bytes are approximate and must not be used for integrity checks. Compare
    the raw token instead; switch to a HEAD request per file if exact sizes
    are ever needed.
    """
    if token == "-":
        return 0
    match = re.fullmatch(r"([\d.]+)([KMGT]?)", token)
    if not match:
        raise CVMPortalError(f"unparseable size token {token!r}")
    return int(float(match.group(1)) * SIZE_UNITS.get(match.group(2), 1))


def crawl_worker_count(override: int | None = None) -> int:
    """Concurrent listing fetches per host. Default is two; never below one."""
    if override is not None:
        value = int(override)
    else:
        env = os.environ.get("CVMDATA_CRAWL_WORKERS") or os.environ.get("CVMPY_CRAWL_WORKERS")
        value = int(env) if env else CRAWL_WORKERS
    if value < 1:
        raise ValueError("crawl workers must be >= 1")
    return value


def listing(url: str, *, getter=None) -> list[tuple[str, str, str]]:
    fetch = http_get if getter is None else getter
    body = fetch(url).decode("utf-8", "replace")
    if "Index of" not in body:
        raise CVMPortalError(f"{url} is not a directory listing")
    return [
        (href, date, size)
        for href, date, size in LISTING_ROW.findall(body)
        if href != "../"
    ]


def walk(url: str, depth: int = 1, *, getter=None) -> list[dict]:
    files: list[dict] = []
    for href, date, size in listing(url, getter=getter):
        if href.endswith("/"):
            if depth < MAX_DEPTH:
                files.extend(walk(url + href, depth + 1, getter=getter))
            continue
        files.append({
            "url": url + href,
            "name": href,
            "modified": parse_listing_date(date),
            "size_raw": size,
            "bytes": parse_size(size),
        })
    return files


def period_of(name: str) -> str:
    found = PERIOD.findall(name)
    return found[-1] if found else ""


def crawl_tree(workers: int | None = None, client: HttpClient | None = None) -> dict[str, dict]:
    """Every dataset under /dados/, keyed by path (e.g. CIA_ABERTA/DOC/ITR)."""
    client = client or HttpClient()

    def getter(url: str) -> bytes:
        return client.fetch_bytes(url).content

    areas = [href for href, _, _ in listing(DATA_ROOT, getter=getter) if href.endswith("/")]
    if not areas:
        raise CVMPortalError("no areas found under /dados/ — portal layout changed")

    datasets: dict[str, dict] = {}
    worker_count = crawl_worker_count(workers)
    with concurrent.futures.ThreadPoolExecutor(worker_count) as pool:
        for area, files in zip(
            areas,
            pool.map(lambda a: walk(DATA_ROOT + a, getter=getter), areas),
        ):
            for entry in files:
                parts = entry["url"][len(DATA_ROOT):].split("/")
                bucket_at = next(
                    (i for i, p in enumerate(parts) if p in ("DADOS", "META")), -1,
                )
                if bucket_at < 1:
                    raise CVMPortalError(f"unexpected path shape: {entry['url']}")
                bucket = parts[bucket_at]
                path = "/".join(parts[:bucket_at])
                ds = datasets.setdefault(path, {
                    "path": path,
                    "area": area.strip("/"),
                    "files": [],
                    "meta": [],
                })
                entry["period"] = period_of(entry["name"]) if bucket == "DADOS" else ""
                entry["archived"] = bucket == "DADOS" and len(parts) > bucket_at + 2
                ds["files" if bucket == "DADOS" else "meta"].append(entry)
    for ds in datasets.values():
        ds["files"].sort(key=lambda f: f["name"])
        ds["meta"].sort(key=lambda f: f["name"])
    return datasets


def fetch_ckan(client: HttpClient | None = None) -> tuple[list[dict], dict[str, str]]:
    getter = (lambda url: client.fetch_bytes(url).content) if client else http_get
    payload = json.loads(getter(CKAN_PACKAGES).decode("utf-8"))
    if not payload.get("success"):
        raise CVMPortalError("CKAN package listing returned success=false")
    packages = []
    for pkg in payload["result"]:
        packages.append({
            "name": pkg["name"],
            "title": pkg.get("title", ""),
            "notes": re.sub(r"\s+", " ", re.sub(r"[_*]", "", pkg.get("notes") or "")).strip(),
            "groups": [g["name"] for g in pkg.get("groups", [])],
            "resources": [
                {
                    "name": r.get("name", ""),
                    "url": r.get("url", ""),
                    "format": r.get("format", ""),
                }
                for r in pkg.get("resources", [])
            ],
        })
    groups_payload = json.loads(getter(CKAN_GROUPS).decode("utf-8"))
    groups = {g["name"]: g["title"] for g in groups_payload.get("result", [])}
    return packages, groups


def link_packages(datasets: dict[str, dict], packages: list[dict]) -> None:
    """Attach CKAN title/notes/groups to each crawled dataset via resource URLs."""
    for pkg in packages:
        matched = set()
        for res in pkg["resources"]:
            url = res["url"]
            if not url.startswith(DATA_ROOT):
                continue
            parts = url[len(DATA_ROOT):].split("/")
            if len(parts) >= 3 and parts[-2] in ("DADOS", "META"):
                matched.add("/".join(parts[:-2]))
        for path in matched:
            ds = datasets.get(path)
            if ds is None:
                continue
            ds.setdefault("package", pkg["name"])
            ds.setdefault("title", pkg["title"])
            ds.setdefault("notes", pkg["notes"])
            ds.setdefault("groups", pkg["groups"])


def build_catalog(workers: int | None = None, client: HttpClient | None = None) -> dict:
    client = client or HttpClient()
    datasets = crawl_tree(workers=workers, client=client)
    packages, groups = fetch_ckan(client=client)
    link_packages(datasets, packages)
    external = [
        p for p in packages
        if p["resources"] and not any(r["url"].startswith(DATA_ROOT) for r in p["resources"])
    ]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": PORTAL,
        "groups": groups,
        "datasets": [datasets[k] for k in sorted(datasets)],
        "external_packages": external,
    }


def show_period(period: str) -> str:
    return f"{period[:4]}-{period[4:]}" if len(period) == 6 else period


def coverage(ds: dict) -> str:
    periods = sorted(
        {f["period"] for f in ds["files"] if f["period"]},
        key=lambda p: p.ljust(6, "0"),
    )
    if not periods:
        return "snapshot"
    first, last = show_period(periods[0]), show_period(periods[-1])
    return first if first == last else f"{first}..{last}"


def span(period: str) -> tuple[str, str]:
    """A period as the closed month interval it covers: 2006 -> 200601..200612."""
    if len(period) == 4:
        return f"{period}01", f"{period}12"
    return period, period


def overlaps(period: str, start: str | None, end: str | None) -> bool:
    """Whether a file's period intersects the requested range.

    Interval overlap, not point comparison: a yearly file must still match a
    monthly range that lands inside it.
    """
    if not period:
        return False
    lo, hi = span(period)
    if start and hi < span(start)[0]:
        return False
    if end and lo > span(end)[1]:
        return False
    return True


def dataset_stats(ds: dict) -> dict:
    return {
        "path": ds["path"],
        "title": ds.get("title", ""),
        "files": len(ds["files"]),
        "bytes": sum(f["bytes"] for f in ds["files"]),
        "coverage": coverage(ds),
        "updated": max((f["modified"] for f in ds["files"]), default=""),
    }


def human(size: int) -> str:
    value: float = float(size)
    for unit in ("B", "K", "M", "G"):
        if value < 1024 or unit == "G":
            return f"{value:.0f}{unit}" if unit == "B" else f"{value:.1f}{unit}"
        value /= 1024
    return f"{value:.1f}G"


def select(catalog: dict, needle: str) -> list[dict]:
    """Datasets matching a path, a path suffix, or a case-insensitive fragment."""
    key = needle.strip("/").upper()
    exact = [d for d in catalog["datasets"] if d["path"].upper() == key]
    if exact:
        return exact
    suffix = [d for d in catalog["datasets"] if d["path"].upper().endswith("/" + key)]
    if suffix:
        return suffix
    return [d for d in catalog["datasets"] if key in d["path"].upper()]


def resolve_dataset(catalog: dict, needle: str) -> dict:
    """Resolve an alias, path, suffix, or fragment to exactly one dataset."""
    alias = DATASETS.get(needle.strip().upper())
    if alias:
        matches = [d for d in catalog["datasets"] if d["path"].upper() == alias.upper()]
        if not matches:
            raise CVMError(
                f"alias {needle!r} maps to {alias} but that path is not in the catalog"
            )
        return matches[0]
    matches = select(catalog, needle)
    if not matches:
        raise CVMError(f"no dataset matched {needle!r} — try list_datasets()")
    if len(matches) > 1:
        names = ", ".join(d["path"] for d in matches)
        raise CVMAmbiguousDatasetError(
            f"{needle!r} matched {names}; be more specific"
        )
    return matches[0]


def selected_files(ds: dict, start: str | None, end: str | None) -> list[dict]:
    if not (start or end):
        return list(ds["files"])
    return [f for f in ds["files"] if overlaps(f["period"], start, end)]


def refresh_catalog(
    cache_dir_path: str | Path | None = None,
    workers: int | None = None,
) -> dict:
    cache = cache_dir(cache_dir_path)
    cache.mkdir(parents=True, exist_ok=True)
    current, previous = catalog_paths(cache)
    catalog = build_catalog(workers=workers)
    if current.exists():
        previous.write_text(current.read_text(encoding="utf-8"), encoding="utf-8")
    current.write_text(json.dumps(catalog, ensure_ascii=False, indent=1), encoding="utf-8")
    return catalog


def list_datasets(
    area: str | None = None,
    grep: str | None = None,
    cache_dir_path: str | Path | None = None,
    catalog: dict | None = None,
) -> list[dict]:
    data = catalog if catalog is not None else load_catalog(cache_dir_path)
    rows = [
        d for d in data["datasets"]
        if (not area or d["area"].upper() == area.upper())
        and (
            not grep
            or grep.lower() in (d["path"] + " " + d.get("title", "")).lower()
        )
    ]
    return sorted((dataset_stats(d) for d in rows), key=lambda s: -s["bytes"])


def show_dataset(
    dataset: str,
    cache_dir_path: str | Path | None = None,
    catalog: dict | None = None,
) -> dict:
    data = catalog if catalog is not None else load_catalog(cache_dir_path)
    return resolve_dataset(data, dataset)


def dataset_urls(
    dataset: str,
    start: str | None = None,
    end: str | None = None,
    dicts: bool = False,
    cache_dir_path: str | Path | None = None,
    catalog: dict | None = None,
) -> list[str]:
    data = catalog if catalog is not None else load_catalog(cache_dir_path)
    ds = resolve_dataset(data, dataset)
    files = selected_files(ds, start, end)
    urls = [f["url"] for f in files]
    if dicts:
        urls = [f["url"] for f in ds["meta"]] + urls
    if not urls:
        raise CVMError(f"{ds['path']} has no files for the requested period")
    return urls


def catalog_diff(cache_dir_path: str | Path | None = None) -> dict:
    cache = cache_dir(cache_dir_path)
    current_path, previous_path = catalog_paths(cache)
    if not previous_path.exists():
        raise CVMCatalogError(
            f"no previous catalog at {previous_path} — refresh_catalog() at least twice"
        )
    current = load_catalog(cache)
    previous = json.loads(previous_path.read_text(encoding="utf-8"))

    def index(cat: dict) -> dict[str, tuple[str, str]]:
        return {
            f["url"]: (f["modified"], f["size_raw"])
            for d in cat["datasets"]
            for f in d["files"] + d["meta"]
        }

    now, before = index(current), index(previous)
    return {
        "previous_generated_at": previous["generated_at"],
        "generated_at": current["generated_at"],
        "added": sorted(now.keys() - before.keys()),
        "changed": sorted(u for u in now.keys() & before.keys() if now[u] != before[u]),
        "removed": sorted(before.keys() - now.keys()),
    }
