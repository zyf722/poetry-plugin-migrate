from __future__ import annotations

import pytest
from tomlkit import TOMLDocument, parse

from poetry_plugin_migrate.migrator import Migrator
from poetry_plugin_migrate.toml import require_array, require_table


class StubCommand:
    def line(self, _message: str = "") -> None:
        pass

    def confirm(self, _question: str, default: bool = False) -> bool:
        return default

    def choice(
        self,
        _question: str,
        choices: list[str],
        default: int,
        _attempts: int | None = None,
        _multiple: bool = False,
    ) -> str:
        return choices[default]


class MovePythonCommand(StubCommand):
    def confirm(self, _question: str, default: bool = False) -> bool:
        return default

    def choice(
        self,
        question: str,
        choices: list[str],
        default: int,
        _attempts: int | None = None,
        _multiple: bool = False,
    ) -> str:
        if "dependencies.python" in question:
            return choices[0]
        return choices[default]


class UpdateBuildRequirementCommand(StubCommand):
    def choice(
        self,
        question: str,
        choices: list[str],
        default: int,
        _attempts: int | None = None,
        _multiple: bool = False,
    ) -> str:
        if "build-system.requires.poetry-core" in question:
            return choices[0]
        return choices[default]


def migrate(source: str) -> tuple[TOMLDocument, Migrator]:
    migrator = Migrator(StubCommand(), skip=True, literal=False)
    return migrator.run(parse(source)), migrator


def test_missing_tool_poetry_is_a_safe_noop() -> None:
    source = """\
[project]
name = "already-modern"
version = "1.0.0"
"""

    result, migrator = migrate(source)

    assert result.as_string() == source
    assert migrator.warnings == [
        "[tool.poetry] section not found. Related migration skipped."
    ]


def test_updated_build_requirement_uses_shared_pep508_renderer() -> None:
    document = parse(
        """\
[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
"""
    )
    migrator = Migrator(UpdateBuildRequirementCommand(), skip=False, literal=False)

    migrator._migrate_build_system(document)

    build_system = require_table(document["build-system"], "build-system")
    assert build_system["requires"] == ["poetry-core>=2.0"]


def test_custom_urls_migrate_without_predefined_url_fields() -> None:
    result, _ = migrate(
        """\
[tool.poetry]
name = "urls-only"

[tool.poetry.urls]
Issues = "https://example.invalid/issues"
Funding = "https://example.invalid/funding"
"""
    )

    project = require_table(result["project"], "project")
    urls = require_table(project["urls"], "project.urls")
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    assert urls == {
        "Issues": "https://example.invalid/issues",
        "Funding": "https://example.invalid/funding",
    }
    assert "urls" not in tool_poetry


def test_authors_and_maintainers_keep_their_roles() -> None:
    result, _ = migrate(
        """\
[tool.poetry]
authors = ["Alice <alice@example.com>"]
maintainers = ["Maria <maria@example.com>"]
"""
    )

    project = require_table(result["project"], "project")
    authors = require_array(project["authors"], "project.authors")
    maintainers = require_array(project["maintainers"], "project.maintainers")
    author = require_table(authors[0], "project.authors[0]")
    maintainer = require_table(maintainers[0], "project.maintainers[0]")
    assert author["name"] == "Alice"
    assert maintainer["name"] == "Maria"


def test_different_target_value_preserves_legacy_source() -> None:
    result, migrator = migrate(
        """\
[project]
name = "modern-name"

[tool.poetry]
name = "legacy-name"
"""
    )

    project = require_table(result["project"], "project")
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    assert project["name"] == "modern-name"
    assert tool_poetry["name"] == "legacy-name"
    assert any("different values" in warning for warning in migrator.warnings)


@pytest.mark.parametrize(
    "intervening_section",
    [
        '[metadata]\nnote = "dummy"',
        '[build-system]\nrequires = ["poetry-core"]\nbuild-backend = "poetry.core.masonry.api"',
        "[tool.isort]\nline_length = 88",
    ],
)
def test_split_poetry_tables_migrate_without_corrupting_tomlkit_indexes(
    intervening_section: str,
) -> None:
    source = f"""\
[tool.poetry]
name = "layout-project"
version = "1.0.0"

{intervening_section}

[tool.poetry.dependencies]
python = ">=3.10,<3.13"
dummy-runtime = "^2.0"

[tool.poetry.group.test]
optional = true

[tool.poetry.group.test.dependencies]
dummy-test = "^3.0"
"""
    migrator = Migrator(MovePythonCommand(), skip=False, literal=False)
    result = migrator.run(parse(source))
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    project = require_table(result["project"], "project")
    dependency_groups = require_table(result["dependency-groups"], "dependency-groups")
    poetry_groups = require_table(tool_poetry["group"], "tool.poetry.group")
    test_group = require_table(poetry_groups["test"], "tool.poetry.group.test")

    assert "dependencies" not in tool_poetry
    assert project["dependencies"] == ["dummy-runtime>=2.0,<3.0"]
    assert dependency_groups["test"] == ["dummy-test>=3.0,<4.0"]
    assert test_group["optional"] is True
    reparsed = parse(result.as_string())
    reparsed_project = require_table(reparsed["project"], "project")
    reparsed_groups = require_table(reparsed["dependency-groups"], "dependency-groups")
    assert reparsed_project.unwrap() == project.unwrap()
    assert reparsed_groups.unwrap() == dependency_groups.unwrap()
    if intervening_section.startswith("[metadata]"):
        metadata = require_table(reparsed["metadata"], "metadata")
        assert metadata["note"] == "dummy"
    elif intervening_section.startswith("[build-system]"):
        build_system = require_table(reparsed["build-system"], "build-system")
        assert build_system["build-backend"] == "poetry.core.masonry.api"
    else:
        reparsed_tool = require_table(reparsed["tool"], "tool")
        isort = require_table(reparsed_tool["isort"], "tool.isort")
        assert isort["line_length"] == 88


def test_split_nested_dependency_and_groups_migrate_together() -> None:
    source = """\
[tool.poetry]
name = "nested-layout"
version = "1.0.0"

[tool.poetry.dependencies]
python = ">=3.10"
dummy-runtime = "^1.0"

[tool.pytest.ini_options]
addopts = "-q"

[tool.poetry.dependencies.dummy-rich]
version = "^2.0"
extras = ["feature"]

[tool.poetry.plugins.pytest11]
dummy = "dummy_plugin"

[tool.poetry.group.dev.dependencies]
dummy-dev = "^4.0"

[tool.poetry.group.docs.dependencies.dummy-docs]
version = "^5.0"
extras = ["docs"]
"""

    result = Migrator(MovePythonCommand(), skip=False, literal=False).run(parse(source))
    project = require_table(result["project"], "project")
    dependency_groups = require_table(result["dependency-groups"], "dependency-groups")
    entry_points = require_table(project["entry-points"], "project.entry-points")
    pytest11 = require_table(entry_points["pytest11"], "project.entry-points.pytest11")
    tool = require_table(result["tool"], "tool")
    pytest_table = require_table(tool["pytest"], "tool.pytest")
    pytest_options = require_table(
        pytest_table["ini_options"], "tool.pytest.ini_options"
    )

    assert project["dependencies"] == [
        "dummy-runtime>=1.0,<2.0",
        "dummy-rich[feature]>=2.0,<3.0",
    ]
    assert dependency_groups["dev"] == ["dummy-dev>=4.0,<5.0"]
    assert dependency_groups["docs"] == ["dummy-docs[docs]>=5.0,<6.0"]
    assert pytest11["dummy"] == "dummy_plugin"
    assert pytest_options["addopts"] == "-q"
    reparsed = parse(result.as_string())
    reparsed_project = require_table(reparsed["project"], "project")
    reparsed_groups = require_table(reparsed["dependency-groups"], "dependency-groups")
    reparsed_tool = require_table(reparsed["tool"], "tool")
    reparsed_pytest = require_table(reparsed_tool["pytest"], "tool.pytest")
    reparsed_options = require_table(
        reparsed_pytest["ini_options"], "tool.pytest.ini_options"
    )
    assert reparsed_project.unwrap() == project.unwrap()
    assert reparsed_groups.unwrap() == dependency_groups.unwrap()
    assert reparsed_options["addopts"] == "-q"


def test_split_table_consolidation_preserves_trivia_and_is_idempotent() -> None:
    source = """\
# document comment
[tool.poetry]
# project-name comment
name = "commented-layout"
version = "1.0.0"

[metadata]
dummy = "untouched"

# unrelated tool comment
[tool.dummy]
enabled = true

# dependency comment
[tool.poetry.dependencies]
python = ">=3.10"
dummy-runtime = "^2.0" # inline dependency comment
"""

    first, _ = migrate(source)
    rendered = first.as_string()
    second, _ = migrate(rendered)

    assert "# document comment" in rendered
    assert "# project-name comment" in rendered
    assert "# unrelated tool comment" in rendered
    assert "# dependency comment" in rendered
    assert "# inline dependency comment" in rendered
    metadata = require_table(first["metadata"], "metadata")
    tool = require_table(first["tool"], "tool")
    dummy_tool = require_table(tool["dummy"], "tool.dummy")
    assert metadata["dummy"] == "untouched"
    assert dummy_tool["enabled"] is True
    assert second.as_string() == rendered
