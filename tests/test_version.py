"""Guardrail: runtime __version__ and packaged metadata version must agree."""

from importlib import metadata

import pytest

import cvmdata


def test_version_matches_package_metadata():
    try:
        dist_version = metadata.version("cvmdata")
    except metadata.PackageNotFoundError:
        pytest.skip("cvmdata is not installed; metadata unavailable")
    assert dist_version == cvmdata.__version__
