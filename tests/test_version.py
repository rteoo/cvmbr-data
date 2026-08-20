"""Guardrail: runtime __version__ and packaged metadata version must agree."""

from importlib import metadata

import pytest

import cvmpy


def test_version_matches_package_metadata():
    try:
        dist_version = metadata.version("cvmpy")
    except metadata.PackageNotFoundError:
        pytest.skip("cvmpy is not installed; metadata unavailable")
    assert dist_version == cvmpy.__version__
