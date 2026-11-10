"""Curated dataset alias invariants."""

import re

from cvmdata.datasets import ALL_DATASETS, CATEGORIES, DATASETS


def test_alias_keys_are_upper_snake():
    pattern = re.compile(r"^[A-Z][A-Z0-9_]*$")
    for key in DATASETS:
        assert pattern.match(key), key


def test_alias_paths_are_unique():
    paths = list(DATASETS.values())
    assert len(paths) == len(set(paths))


def test_categories_cover_all_aliases():
    merged = {}
    for group in CATEGORIES.values():
        merged.update(group)
    assert merged == DATASETS
    assert ALL_DATASETS is DATASETS


def test_core_aliases_point_at_expected_paths():
    assert DATASETS["ITR"] == "CIA_ABERTA/DOC/ITR"
    assert DATASETS["DFP"] == "CIA_ABERTA/DOC/DFP"
    assert DATASETS["INF_DIARIO"] == "FI/DOC/INF_DIARIO"
    assert DATASETS["CDA"] == "FI/DOC/CDA"
    assert DATASETS["CAD"] == "CIA_ABERTA/CAD"
