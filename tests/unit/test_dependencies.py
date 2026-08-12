from __future__ import annotations

from email.parser import Parser
from pathlib import Path
from zipfile import ZipFile

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from poetry.core.masonry.builders.wheel import WheelBuilder
from poetry.core.packages.dependency import Dependency
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


def test_dependencies_are_multiline_and_generated_without_brackets() -> None:
    result, _ = migrate(
        """\
[tool.poetry.dependencies]
python = "^3.10"
requests = "^2.32"
httpx = "^0.28"
"""
    )

    output = result.as_string()
    assert "dependencies = [\n" in output
    assert "requests>=2.32,<3.0" in output
    assert "requests (" not in output
    project = require_table(result["project"], "project")
    dependencies = require_array(project["dependencies"], "project.dependencies")
    for requirement in dependencies:
        assert isinstance(requirement, str)
        Dependency.create_from_pep_508(requirement)


def test_existing_project_dependency_array_becomes_multiline() -> None:
    result, _ = migrate(
        """\
[project]
dependencies = ["click>=8"]

[tool.poetry.dependencies]
python = "^3.10"
requests = "^2.32"
"""
    )

    assert "dependencies = [\n" in result.as_string()


def test_optional_dependency_arrays_are_multiline() -> None:
    result, _ = migrate(
        """\
[tool.poetry.extras]
networking = ["requests", "httpx"]

[tool.poetry.dependencies]
python = "^3.10"
requests = { version = "^2.32", optional = true }
httpx = { version = "^0.28", optional = true }
"""
    )

    output = result.as_string()
    assert "networking = [\n" in output
    assert "requests>=2.32,<3.0" in output
    assert "httpx>=0.28,<0.29" in output
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    dependencies = require_table(
        tool_poetry["dependencies"], "tool.poetry.dependencies"
    )
    assert "requests" not in dependencies
    assert "httpx" not in dependencies


def test_multiple_optional_constraints_do_not_leak_between_packages() -> None:
    result, _ = migrate(
        """\
[tool.poetry.extras]
first = ["alpha"]
second = ["beta"]

[tool.poetry.dependencies]
python = "^3.10"
alpha = [
    { version = "^1", optional = true, platform = "win32" },
    { version = "^2", optional = true, platform = "linux" },
]
beta = { version = "^3", optional = true, python = ">=3.11" }
"""
    )

    project = require_table(result["project"], "project")
    optional = require_table(
        project["optional-dependencies"], "project.optional-dependencies"
    )
    first = list(
        require_array(optional["first"], "project.optional-dependencies.first")
    )
    second = list(
        require_array(optional["second"], "project.optional-dependencies.second")
    )
    assert len(first) == 2
    assert all(
        isinstance(requirement, str) and requirement.startswith("alpha")
        for requirement in first
    )
    assert second == ['beta>=3,<4 ; python_version >= "3.11"']


def test_relative_path_keeps_complete_dependency_model(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    local_package = tmp_path / "dummy-local"
    local_package.mkdir()
    (local_package / "pyproject.toml").write_text(
        """\
[project]
name = "dummy-local"
version = "1.0.0"
"""
    )
    project = tmp_path / "dummy-app"
    project.mkdir()
    source = """\
[tool.poetry]
name = "dummy-app"
version = "1.0.0"
description = "Synthetic dependency preservation project"
authors = []

[tool.poetry.dependencies]
python = ">=3.10"
dummy-runtime = "^2.0"
dummy-local = { path = "../dummy-local", develop = true }
dummy-optional = { version = "^3.0", optional = true }

[tool.poetry.extras]
feature = ["dummy-optional"]
"""
    pyproject = project / "pyproject.toml"
    pyproject.write_text(source)
    monkeypatch.chdir(project)

    before = Factory().create_poetry(project)
    before_requirements = sorted(
        dependency.to_pep_508() for dependency in before.package.requires
    )

    result, migrator = migrate(source)
    pyproject.write_text(result.as_string())
    after = Factory().create_poetry(project)
    after_requirements = sorted(
        dependency.to_pep_508() for dependency in after.package.requires
    )

    assert after_requirements == before_requirements
    migrated_project = require_table(result["project"], "project")
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    dependencies = require_table(
        tool_poetry["dependencies"], "tool.poetry.dependencies"
    )
    extras = require_table(tool_poetry["extras"], "tool.poetry.extras")
    assert migrated_project["dynamic"] == ["dependencies"]
    assert migrated_project["requires-python"] == ">=3.10"
    assert dependencies["dummy-runtime"] == "^2.0"
    assert dependencies["dummy-local"] == {
        "path": "../dummy-local",
        "develop": True,
    }
    assert dependencies["dummy-optional"] == {
        "version": "^3.0",
        "optional": True,
    }
    assert extras["feature"] == ["dummy-optional"]
    assert any("All dependencies and extras were kept" in w for w in migrator.warnings)


def test_relative_path_with_existing_project_dependencies_aborts() -> None:
    source = """\
[project]
name = "mixed-declarations"
version = "1.0.0"
dependencies = ["dummy-modern>=1"]

[tool.poetry]

[tool.poetry.dependencies]
python = ">=3.10"
dummy-local = { path = "../dummy-local" }
"""

    with pytest.raises(ValueError, match="Cannot safely migrate Poetry dependencies"):
        migrate(source)


def test_poetry_only_dependency_fields_keep_complete_effective_model(
    tmp_path: Path,
) -> None:
    project = tmp_path / "dummy-private-app"
    project.mkdir()
    source = """\
[tool.poetry]
name = "dummy-private-app"
version = "1.0.0"
description = "Synthetic private source preservation"
authors = []

[[tool.poetry.source]]
name = "dummy-private"
url = "https://example.invalid/simple"
priority = "explicit"

[tool.poetry.dependencies]
python = ">=3.10"
dummy-private = { version = "^1.0", source = "dummy-private", allow-prereleases = true }
"""
    pyproject = project / "pyproject.toml"
    pyproject.write_text(source)

    before_dependency = Factory().create_poetry(project).package.requires[0]
    result, migrator = migrate(source)
    pyproject.write_text(result.as_string())
    after_dependency = Factory().create_poetry(project).package.requires[0]

    assert after_dependency.to_pep_508() == before_dependency.to_pep_508()
    assert after_dependency.source_name == before_dependency.source_name
    assert (
        after_dependency.allows_prereleases() is before_dependency.allows_prereleases()
    )
    migrated_project = require_table(result["project"], "project")
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    dependencies = require_table(
        tool_poetry["dependencies"], "tool.poetry.dependencies"
    )
    assert migrated_project["dynamic"] == ["dependencies"]
    assert dependencies["dummy-private"] == {
        "version": "^1.0",
        "source": "dummy-private",
        "allow-prereleases": True,
    }
    assert any("allow-prereleases" in warning for warning in migrator.warnings)


def test_dependency_comments_survive_all_standardized_destinations() -> None:
    result, _ = migrate(
        """\
[tool.poetry]
name = "dummy-comments"
version = "1.0.0"

[tool.synthetic]
enabled = true

[tool.poetry.extras]
feature = ["dummy-optional"]

[tool.poetry.dependencies]
python = ">=3.10"
dummy-runtime = "^1.0" # main dependency note
dummy-optional = { version = "^2.0", optional = true } # optional dependency note

[tool.poetry.group.test.dependencies]
dummy-test = "^3.0" # group dependency note
"""
    )

    rendered = result.as_string()
    reparsed = parse(rendered)

    assert "# main dependency note" in rendered
    assert "# optional dependency note" in rendered
    assert "# group dependency note" in rendered
    require_table(reparsed["project"], "project")
    require_table(reparsed["dependency-groups"], "dependency-groups")


def _requires_dist(wheel: Path) -> set[str]:
    with ZipFile(wheel) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = Parser().parsestr(archive.read(metadata_name).decode())
    return set(metadata.get_all("Requires-Dist", []))


def _requirement_semantics(requirements: set[str]) -> set[tuple[object, ...]]:
    result: set[tuple[object, ...]] = set()
    for raw_requirement in requirements:
        requirement = Requirement(raw_requirement)
        result.add(
            (
                canonicalize_name(requirement.name),
                tuple(sorted(requirement.extras)),
                str(requirement.specifier),
                requirement.url,
                str(requirement.marker) if requirement.marker else None,
            )
        )
    return result


def test_migration_preserves_wheel_dependency_metadata(tmp_path: Path) -> None:
    project = tmp_path / "metadata-app"
    package = project / "dummy_metadata_app"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    source = """\
[tool.poetry]
name = "dummy-metadata-app"
version = "1.0.0"
description = "Synthetic wheel metadata comparison"
authors = []
packages = [{ include = "dummy_metadata_app" }]

[tool.poetry.dependencies]
python = ">=3.10"
dummy-runtime = "^2.0"
dummy-feature = { version = "~3.1", extras = ["speed"] }
dummy-marker = { version = ">=4,<5", markers = "sys_platform == 'win32'" }
dummy-url = { url = "https://example.invalid/dummy_url-5.0-py3-none-any.whl" }
"""
    pyproject = project / "pyproject.toml"
    pyproject.write_text(source)

    before_poetry = Factory().create_poetry(project)
    before_wheel = WheelBuilder(before_poetry).build(tmp_path / "before-dist")

    result, _ = migrate(source)
    pyproject.write_text(result.as_string())
    after_poetry = Factory().create_poetry(project)
    after_wheel = WheelBuilder(after_poetry).build(tmp_path / "after-dist")

    assert _requirement_semantics(
        _requires_dist(after_wheel)
    ) == _requirement_semantics(_requires_dist(before_wheel))
