"""Package-level consistency tests — guard against metadata drift."""

from importlib import metadata

import pytest

import cvmpy


def test_version_matches_installed_distribution():
    try:
        dist_version = metadata.version("cvmpy")
    except metadata.PackageNotFoundError:
        pytest.skip("cvmpy is not installed as a distribution")
    assert cvmpy.__version__ == dist_version


def test_public_api_is_importable():
    for name in cvmpy.__all__:
        assert hasattr(cvmpy, name), f"{name} listed in __all__ but missing"


def test_exceptions_form_a_hierarchy():
    assert issubclass(cvmpy.CVMPortalError, cvmpy.CVMError)
    assert issubclass(cvmpy.CVMEmptyResponseError, cvmpy.CVMError)
    assert issubclass(cvmpy.CVMAmbiguousDatasetError, cvmpy.CVMError)
    assert issubclass(cvmpy.CVMCatalogError, cvmpy.CVMError)
