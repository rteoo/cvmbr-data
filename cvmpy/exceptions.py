"""Exception hierarchy for cvmpy."""

from __future__ import annotations


class CVMError(Exception):
    """Base exception for CVM client errors."""


class CVMPortalError(CVMError):
    """The portal answered in a shape this client cannot trust."""


class CVMEmptyResponseError(CVMError):
    """A query matched no rows or no files."""


class CVMAmbiguousDatasetError(CVMError):
    """A dataset needle matched more than one catalog path."""


class CVMCatalogError(CVMError):
    """The local catalog is missing or unusable."""
