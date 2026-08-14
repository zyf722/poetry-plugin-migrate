from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest
from cleo.testers.application_tester import ApplicationTester
from poetry.console.application import Application
from poetry.factory import Factory
from tomlkit import parse

from poetry_plugin_migrate.command import MigrateCommand
from poetry_plugin_migrate.toml import require_table

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize("project", ["poetry18", "simple-project"], indirect=True)
def test_poetry_loads_plugin(application_tester: ApplicationTester) -> None:
    """Poetry should work with the plugin for test projects."""
    application_tester.execute("migrate -h")
    assert application_tester.status_code == 0
    assert "migrate" in application_tester.io.fetch_output()


@pytest.mark.parametrize("project", ["poetry18", "simple-project"], indirect=True)
@pytest.mark.parametrize("expected_file", ["non-interactive"], indirect=True)
def test_non_interactive(
    application_tester: ApplicationTester, pyproject_file: Path, expected_file: Path
) -> None:
    application_tester.execute("migrate -n --no-backup")
    assert application_tester.status_code == 0

    actual = pyproject_file.read_text()
    expected = expected_file.read_text()

    # tomlkit 0.15.1 removes one redundant blank line that older releases keep
    # when a table is moved. Compare the TOML structure strictly and normalize
    # only runs of blank lines before table headers for the formatting snapshot.
    assert parse(actual).unwrap() == parse(expected).unwrap()

    def normalize_table_spacing(value: str) -> str:
        return re.sub(r"\n{3,}(?=\[)", "\n\n", value)

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


def test_noop_dry_run_still_prints_the_unchanged_document(tmp_path: Path) -> None:
    project = tmp_path / "dummy-non-package"
    project.mkdir()
    pyproject = project / "pyproject.toml"
    source = """\
[tool.poetry]
package-mode = false
"""
    pyproject.write_text(source)
    app = Application()
    app._poetry = Factory().create_poetry(project)
    app.add(MigrateCommand())
    tester = ApplicationTester(app)

    status = tester.execute("migrate -n --no-check --dry-run")

    assert status == 0
    output = tester.io.fetch_output()
    assert "[tool.poetry]" in output
    assert "package-mode = false" in output
    assert pyproject.read_text() == source
    assert not pyproject.with_name("pyproject.bak.toml").exists()


@pytest.mark.parametrize("project", ["simple-project"], indirect=True)
def test_default_migration_creates_exact_backup(
    application_tester: ApplicationTester, pyproject_file: Path
) -> None:
    original = pyproject_file.read_bytes()

    application_tester.execute("migrate -n --no-check")

    assert application_tester.status_code == 0
    assert pyproject_file.read_bytes() != original
    assert pyproject_file.with_name("pyproject.bak.toml").read_bytes() == original


@pytest.mark.parametrize("project", ["simple-project"], indirect=True)
def test_existing_backup_is_preserved(
    application_tester: ApplicationTester, pyproject_file: Path
) -> None:
    original = pyproject_file.read_bytes()
    first_backup = pyproject_file.with_name("pyproject.bak.toml")
    first_backup.write_text("existing backup")

    application_tester.execute("migrate -n --no-check")

    assert application_tester.status_code == 0
    assert first_backup.read_text() == "existing backup"
    assert pyproject_file.with_name("pyproject.bak.1.toml").read_bytes() == original


@pytest.mark.parametrize("project", ["simple-project"], indirect=True)
def test_invalid_generated_file_is_not_written_or_backed_up(
    application_tester: ApplicationTester,
    pyproject_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = pyproject_file.read_bytes()

    def invalid_result(self: object, document: object) -> object:
        del self, document
        return parse("[project]\nname = 'missing-version'\n")

    monkeypatch.setattr("poetry_plugin_migrate.command.Migrator.run", invalid_result)
    application_tester.execute("migrate -n --no-check")

    assert application_tester.status_code == 1
    assert pyproject_file.read_bytes() == original
    assert not pyproject_file.with_name("pyproject.bak.toml").exists()


def test_dependency_conflict_aborts_before_backup_or_write(tmp_path: Path) -> None:
    project = tmp_path / "dummy-conflict"
    project.mkdir()
    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        """\
[project]
name = "dummy-conflict"
version = "1.0.0"
dependencies = ["dummy-standard>=1"]

[tool.poetry.dependencies]
python = ">=3.10"
dummy-legacy = "^2"
"""
    )
    original = pyproject.read_bytes()
    app = Application()
    app._poetry = Factory().create_poetry(project)
    app.add(MigrateCommand())
    tester = ApplicationTester(app)

    status = tester.execute("migrate -n --no-check")

    assert status == 1
    assert "Cannot safely migrate Poetry dependencies" in tester.io.fetch_error()
    assert pyproject.read_bytes() == original
    assert not pyproject.with_name("pyproject.bak.toml").exists()


def test_interactive_cli_migrates_split_tables_with_nested_dependencies(
    tmp_path: Path,
) -> None:
    project = tmp_path / "dummy-layout-project"
    project.mkdir()
    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        """\
[tool.poetry]
name = "dummy-layout-project"
version = "1.0.0"
description = "Synthetic CLI regression project"
authors = []

[tool.coverage.run]
branch = true

[tool.poetry.dependencies]
python = ">=3.10"
dummy-runtime = "^2.0"

[tool.pytest.ini_options]
addopts = "-q"

[tool.poetry.dependencies.dummy-rich]
version = "^3.0"
extras = ["feature"]

[tool.poetry.group.test]
optional = true

[tool.poetry.group.test.dependencies]
dummy-test = "^4.0"
"""
    )
    app = Application()
    app._poetry = Factory().create_poetry(project)
    app.add(MigrateCommand())
    tester = ApplicationTester(app)

    status = tester.execute(
        "migrate --no-backup",
        inputs="no\nyes\n0\nno\n2\nno\n",
        interactive=True,
    )

    assert status == 0
    assert "list index out of range" not in tester.io.fetch_error()
    migrated = parse(pyproject.read_text())
    migrated_project = require_table(migrated["project"], "project")
    dependency_groups = require_table(
        migrated["dependency-groups"], "dependency-groups"
    )
    tool = require_table(migrated["tool"], "tool")
    coverage = require_table(tool["coverage"], "tool.coverage")
    coverage_run = require_table(coverage["run"], "tool.coverage.run")
    pytest_table = require_table(tool["pytest"], "tool.pytest")
    pytest_options = require_table(
        pytest_table["ini_options"], "tool.pytest.ini_options"
    )
    assert migrated_project["dependencies"] == [
        "dummy-runtime>=2.0,<3.0",
        "dummy-rich[feature]>=3.0,<4.0",
    ]
    assert dependency_groups["test"] == ["dummy-test>=4.0,<5.0"]
    assert coverage_run["branch"] is True
    assert pytest_options["addopts"] == "-q"
    assert Factory().create_poetry(project).package.name == "dummy-layout-project"
