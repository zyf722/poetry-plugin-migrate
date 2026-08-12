from __future__ import annotations

from pathlib import Path

from poetry.factory import Factory
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


def migrate(source: str) -> tuple[TOMLDocument, Migrator]:
    migrator = Migrator(StubCommand(), skip=True, literal=False)
    return migrator.run(parse(source)), migrator


def test_groups_dependencies_includes_and_optional_metadata_migrate() -> None:
    result, _ = migrate(
        """\
[tool.poetry.group.test]
optional = true
include-groups = ["lint"]

[tool.poetry.group.test.dependencies]
pytest = "^8.3"

[tool.poetry.group.lint.dependencies]
ruff = "^0.15"
"""
    )

    dependency_groups = require_table(result["dependency-groups"], "dependency-groups")
    test_group = require_array(dependency_groups["test"], "dependency-groups.test")
    include_group = require_table(test_group[0], "dependency-groups.test[0]")
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    poetry_groups = require_table(tool_poetry["group"], "tool.poetry.group")
    poetry_test = require_table(poetry_groups["test"], "tool.poetry.group.test")
    assert include_group["include-group"] == "lint"
    assert test_group[1] == "pytest>=8.3,<9.0"
    assert dependency_groups["lint"] == ["ruff>=0.15,<0.16"]
    assert poetry_test == {"optional": True}
    assert "lint" not in poetry_groups


def test_legacy_dev_dependencies_migrate() -> None:
    result, _ = migrate(
        """\
[tool.poetry.dev-dependencies]
pytest = "^8.3"
"""
    )

    dependency_groups = require_table(result["dependency-groups"], "dependency-groups")
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    assert dependency_groups["dev"] == ["pytest>=8.3,<9.0"]
    assert "dev-dependencies" not in tool_poetry


def test_poetry_only_group_dependency_keeps_whole_group() -> None:
    source = """\
[[tool.poetry.source]]
name = "private"
url = "https://example.invalid/simple"
priority = "supplemental"

[tool.poetry.group.private.dependencies]
internal = { version = "^1.0", source = "private" }
"""
    result, migrator = migrate(source)

    assert "dependency-groups" not in result
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    groups = require_table(tool_poetry["group"], "tool.poetry.group")
    private_group = require_table(groups["private"], "tool.poetry.group.private")
    dependencies = require_table(
        private_group["dependencies"], "tool.poetry.group.private.dependencies"
    )
    internal = require_table(
        dependencies["internal"],
        "tool.poetry.group.private.dependencies.internal",
    )
    assert internal["source"] == "private"
    assert any(
        "Poetry-only fields (source)" in warning for warning in migrator.warnings
    )


def test_relative_path_dependency_keeps_whole_group() -> None:
    result, migrator = migrate(
        """\
[tool.poetry.group.local.dependencies]
dummy-local = { path = "../dummy-local", develop = true }
"""
    )

    assert "dependency-groups" not in result
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    groups = require_table(tool_poetry["group"], "tool.poetry.group")
    local_group = require_table(groups["local"], "tool.poetry.group.local")
    dependencies = require_table(
        local_group["dependencies"], "tool.poetry.group.local.dependencies"
    )
    assert dependencies["dummy-local"] == {
        "path": "../dummy-local",
        "develop": True,
    }
    assert any("relative path" in warning for warning in migrator.warnings)


def test_existing_target_group_preserves_legacy_group() -> None:
    result, migrator = migrate(
        """\
[dependency-groups]
test = ["pytest>=8"]

[tool.poetry.group.test.dependencies]
pytest = "^7"
"""
    )

    dependency_groups = require_table(result["dependency-groups"], "dependency-groups")
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    groups = require_table(tool_poetry["group"], "tool.poetry.group")
    assert dependency_groups["test"] == ["pytest>=8"]
    assert "test" in groups
    assert any("already exists" in warning for warning in migrator.warnings)


def test_normalized_target_group_conflict_preserves_legacy_group() -> None:
    result, migrator = migrate(
        """\
[dependency-groups]
test-group = ["pytest>=8"]

[tool.poetry.group.test_group.dependencies]
pytest = "^7"
"""
    )

    dependency_groups = require_table(result["dependency-groups"], "dependency-groups")
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    groups = require_table(tool_poetry["group"], "tool.poetry.group")
    assert list(dependency_groups) == ["test-group"]
    assert "test_group" in groups
    assert any("equivalent normalized name" in warning for warning in migrator.warnings)


def test_migrated_groups_are_accepted_by_poetry(tmp_path: Path) -> None:
    result, _ = migrate(
        """\
[tool.poetry]
name = "group-project"
version = "1.0.0"
description = "Dependency group schema test"
authors = []

[tool.poetry.dependencies]
python = ">=3.10"

[tool.poetry.group.test]
optional = true
include-groups = ["lint"]

[tool.poetry.group.test.dependencies]
pytest = "^8.3"

[tool.poetry.group.lint.dependencies]
ruff = "^0.15"
"""
    )
    (tmp_path / "pyproject.toml").write_text(result.as_string())

    poetry = Factory().create_poetry(tmp_path)

    assert poetry.package.name == "group-project"
