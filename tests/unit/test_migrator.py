from __future__ import annotations

from typing import Any, cast

from tomlkit import parse

from poetry_plugin_migrate.migrator import Migrator


class StubCommand:
    def line(self, _message: str = "") -> None:
        pass


class MovePythonCommand(StubCommand):
    def confirm(self, _question: str, default: bool) -> bool:
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


def migrate(source: str):
    migrator = Migrator(StubCommand(), skip=True, literal=False)  # type: ignore[arg-type]
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

    assert result["project"]["urls"] == {
        "Issues": "https://example.invalid/issues",
        "Funding": "https://example.invalid/funding",
    }
    assert "urls" not in result["tool"]["poetry"]


def test_authors_and_maintainers_keep_their_roles() -> None:
    result, _ = migrate(
        """\
[tool.poetry]
authors = ["Alice <alice@example.com>"]
maintainers = ["Maria <maria@example.com>"]
"""
    )

    assert result["project"]["authors"][0]["name"] == "Alice"
    assert result["project"]["maintainers"][0]["name"] == "Maria"


def test_different_target_value_preserves_legacy_source() -> None:
    result, migrator = migrate(
        """\
[project]
name = "modern-name"

[tool.poetry]
name = "legacy-name"
"""
    )

    assert result["project"]["name"] == "modern-name"
    assert result["tool"]["poetry"]["name"] == "legacy-name"
    assert any("different values" in warning for warning in migrator.warnings)


def test_issue_1_nested_dependencies_do_not_corrupt_tomlkit_indexes() -> None:
    source = """\
[tool.poetry]
name = "issue-one"
version = "3.3.0"

[tool.poetry.dependencies]
python = ">=3.10,<3.13"
bson = "^0.5.10"
numpy = "^2.2.4"
pillow = "^11.1.0"

[tool.poetry.group.test]
optional = true

[tool.poetry.group.test.dependencies]
pytest = "^8.3.5"
pytest-cov = "^6.0.0"
"""
    migrator = Migrator(
        cast(Any, MovePythonCommand()),
        skip=False,
        literal=False,
    )
    result = migrator.run(parse(source))
    tool_poetry = cast(Any, result["tool"])["poetry"]
    project = cast(Any, result["project"])
    dependency_groups = cast(Any, result["dependency-groups"])

    assert "dependencies" not in tool_poetry
    assert project["dependencies"]
    assert dependency_groups["test"]
    assert tool_poetry["group"]["test"]["optional"] is True
