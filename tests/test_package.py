"""Package-level consistency tests — guard against metadata drift."""

from importlib import metadata

import pytest

import cvmdata


def test_version_matches_installed_distribution():
    try:
        dist_version = metadata.version("cvmdata")
    except metadata.PackageNotFoundError:
        pytest.skip("cvmdata is not installed as a distribution")
    assert cvmdata.__version__ == dist_version


def test_public_api_is_importable():
    for name in cvmdata.__all__:
        assert hasattr(cvmdata, name), f"{name} listed in __all__ but missing"


def test_exceptions_form_a_hierarchy():
    assert issubclass(cvmdata.CVMPortalError, cvmdata.CVMError)
    assert issubclass(cvmdata.CVMEmptyResponseError, cvmdata.CVMError)
    assert issubclass(cvmdata.CVMAmbiguousDatasetError, cvmdata.CVMError)
    assert issubclass(cvmdata.CVMCatalogError, cvmdata.CVMError)
