from __future__ import annotations

import configparser
from pathlib import Path


def test_legacy_dashboard_tests_are_excluded_from_default_pytest() -> None:
    parser = configparser.ConfigParser()
    parser.read(Path("pytest.ini"), encoding="utf-8")

    ignored_dirs = set(parser["pytest"]["norecursedirs"].split())

    assert "legacy" in ignored_dirs
    assert "tests/legacy" in ignored_dirs

