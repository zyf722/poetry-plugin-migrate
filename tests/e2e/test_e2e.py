from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from tomlkit import parse

if TYPE_CHECKING:
    from pathlib import Path

    from cleo.testers.application_tester import ApplicationTester


@pytest.mark.parametrize("project", ["poetry18", "simple-project"], indirect=True)
def test_poetry_loads_plugin(application_tester: ApplicationTester):
    """Poetry should work with the plugin for test projects."""
    application_tester.execute("migrate -h")
    assert application_tester.status_code == 0
    assert "migrate" in application_tester.io.fetch_output()


@pytest.mark.parametrize("project", ["poetry18", "simple-project"], indirect=True)
@pytest.mark.parametrize("expected_file", ["non-interactive"], indirect=True)
def test_non_interactive(
    application_tester: ApplicationTester, pyproject_file: Path, expected_file: Path
):
    application_tester.execute("migrate -n --no-backup")
    assert application_tester.status_code == 0

    actual = pyproject_file.read_text()
    expected = expected_file.read_text()

    # tomlkit 0.15.1 removes one redundant blank line that older releases keep
    # when a table is moved. Compare the TOML structure strictly and normalize
    # only runs of blank lines before table headers for the formatting snapshot.
    assert parse(actual).unwrap() == parse(expected).unwrap()
    normalize_table_spacing = lambda value: re.sub(  # noqa: E731
        r"\n{3,}(?=\[)", "\n\n", value
    )
    assert normalize_table_spacing(actual) == normalize_table_spacing(expected)
    assert ", ," not in actual


@pytest.mark.parametrize("project", ["simple-project"], indirect=True)
def test_dry_run_does_not_write_or_create_backup(
    application_tester: ApplicationTester, pyproject_file: Path
) -> None:
    original = pyproject_file.read_bytes()

    application_tester.execute("migrate -n --no-check --dry-run")

    assert application_tester.status_code == 0
    assert pyproject_file.read_bytes() == original
    assert not pyproject_file.with_name("pyproject.bak.toml").exists()
    assert "[project]" in application_tester.io.fetch_output()


@pytest.mark.parametrize("project", ["simple-project"], indirect=True)
def test_default_migration_creates_exact_backup(
    application_tester: ApplicationTester, pyproject_file: Path
) -> None:
    original = pyproject_file.read_bytes()

    application_tester.execute("migrate -n --no-check")

    assert application_tester.status_code == 0
    assert pyproject_file.read_bytes() != original
    assert pyproject_file.with_name("pyproject.bak.toml").read_bytes() == original
