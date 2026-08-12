from __future__ import annotations

from pathlib import Path

from poetry.factory import Factory
from tomlkit import parse

from poetry_plugin_migrate.migrator import Migrator


class StubCommand:
    def line(self, _message: str = "") -> None:
        pass


def migrate(source: str):
    migrator = Migrator(StubCommand(), skip=True, literal=False)  # type: ignore[arg-type]
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

    test_group = result["dependency-groups"]["test"]
    assert test_group[0]["include-group"] == "lint"
    assert test_group[1] == "pytest>=8.3,<9.0"
    assert result["dependency-groups"]["lint"] == ["ruff>=0.15,<0.16"]
    assert result["tool"]["poetry"]["group"]["test"] == {"optional": True}
    assert "lint" not in result["tool"]["poetry"]["group"]


def test_legacy_dev_dependencies_migrate() -> None:
    result, _ = migrate(
        """\
[tool.poetry.dev-dependencies]
pytest = "^8.3"
"""
    )

    assert result["dependency-groups"]["dev"] == ["pytest>=8.3,<9.0"]
    assert "dev-dependencies" not in result["tool"]["poetry"]


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
    assert (
        result["tool"]["poetry"]["group"]["private"]["dependencies"]["internal"][
            "source"
        ]
        == "private"
    )
    assert any(
        "Poetry-only fields (source)" in warning for warning in migrator.warnings
    )


def test_existing_target_group_preserves_legacy_group() -> None:
    result, migrator = migrate(
        """\
[dependency-groups]
test = ["pytest>=8"]

[tool.poetry.group.test.dependencies]
pytest = "^7"
"""
    )

    assert result["dependency-groups"]["test"] == ["pytest>=8"]
    assert "test" in result["tool"]["poetry"]["group"]
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

    assert list(result["dependency-groups"]) == ["test-group"]
    assert "test_group" in result["tool"]["poetry"]["group"]
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
