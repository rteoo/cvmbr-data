# cvmdata release preparation

The repository, distribution, and import package are named `cvmdata`.
The first prepared release under this name is **0.3.0**. Preparing these files
does not publish a package or change repository visibility.

## Migration

Change `from cvmpy ...` to `from cvmdata ...` and install the new distribution
once published. This client is independent of the unrelated `cvmpy` project
already on PyPI. The wheel intentionally ships only the `cvmdata` namespace.

The default cache directory remains `%LOCALAPPDATA%/cvmpy` on Windows and
`~/.cache/cvmpy` elsewhere, so existing archives and catalogs are reused.
No cache files are renamed or removed. `cache_dir_path=` overrides
`CVMDATA_CACHE`, which overrides legacy `CVMPY_CACHE`.
`workers=` overrides `CVMDATA_CRAWL_WORKERS`, which overrides legacy
`CVMPY_CRAWL_WORKERS`. Invalid configured values remain errors.

The parser version, dataset aliases, CSV hygiene, and public function signatures
are unchanged. HTTP user agents and source library versions use the new identity.

## GitHub and PyPI

Rename `rteoo/cvmpy` to `rteoo/cvmdata`, preserving its repository ID, private
visibility, refs, and controls. The rollback is renaming the same repository
back to `cvmpy`. Update origins to `https://github.com/rteoo/cvmdata.git`;
existing checkout folders can stay in place.

Register a pending Trusted Publisher on PyPI with:

| Project | Owner | Repository | Workflow | Environment |
|---|---|---|---|---|
| `cvmdata` | `rteoo` | `cvmdata` | `publish.yml` | `pypi` |

Create and protect the `pypi` GitHub environment before any publication. These
files do not create it or prove its approval rules. A pending publisher does not
reserve the project name. Source and artifact review and the public-visibility
decision remain separate from the repository rename.

## Checks and release

```bash
python -m pytest -m "not integration"
python -m build
python -m twine check --strict dist/*
python release.py --tag v0.3.0 --dry-run
```

The release helper requires clean `main` matching freshly fetched `origin/main`,
a matching source version, and passing offline tests/builds. Run it only after
the patch is reviewed and merged. The publishing workflow additionally checks
the tag, tests, and distribution metadata. It runs only for a published final
GitHub Release in `rteoo/cvmdata`; ordinary pushes, tags, and prereleases do not
publish. Live portal tests remain deliberate opt-in checks.

Publication is a separate action. Existing files and tags are not deleted or
rewritten to perform this migration; PyPI releases are immutable.
