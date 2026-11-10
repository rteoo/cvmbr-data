"""Guardrail: runtime __version__ and packaged metadata version must agree."""

from importlib import metadata

import pytest

import cvmbr_data


def test_version_matches_package_metadata():
    try:
        dist_version = metadata.version("cvmbr-data")
    except metadata.PackageNotFoundError:
        pytest.skip("cvmbr_data is not installed; metadata unavailable")
    assert dist_version == cvmbr_data.__version__
