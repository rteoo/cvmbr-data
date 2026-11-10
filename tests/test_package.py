"""Package-level consistency tests — guard against metadata drift."""

from importlib import metadata

import pytest

import cvmbr_data


def test_version_matches_installed_distribution():
    try:
        dist_version = metadata.version("cvmbr-data")
    except metadata.PackageNotFoundError:
        pytest.skip("cvmbr_data is not installed as a distribution")
    assert cvmbr_data.__version__ == dist_version


def test_public_api_is_importable():
    for name in cvmbr_data.__all__:
        assert hasattr(cvmbr_data, name), f"{name} listed in __all__ but missing"


def test_exceptions_form_a_hierarchy():
    assert issubclass(cvmbr_data.CVMPortalError, cvmbr_data.CVMError)
    assert issubclass(cvmbr_data.CVMEmptyResponseError, cvmbr_data.CVMError)
    assert issubclass(cvmbr_data.CVMAmbiguousDatasetError, cvmbr_data.CVMError)
    assert issubclass(cvmbr_data.CVMCatalogError, cvmbr_data.CVMError)
