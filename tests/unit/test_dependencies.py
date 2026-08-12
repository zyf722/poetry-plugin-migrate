from __future__ import annotations

from poetry.core.packages.dependency import Dependency
from tomlkit import parse

from poetry_plugin_migrate.migrator import Migrator


class StubCommand:
    def line(self, _message: str = "") -> None:
        pass


def migrate(source: str):
    migrator = Migrator(StubCommand(), skip=True, literal=False)  # type: ignore[arg-type]
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
    for requirement in result["project"]["dependencies"]:
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
    assert "requests" not in result["tool"]["poetry"]["dependencies"]
    assert "httpx" not in result["tool"]["poetry"]["dependencies"]


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

    first = list(result["project"]["optional-dependencies"]["first"])
    second = list(result["project"]["optional-dependencies"]["second"])
    assert len(first) == 2
    assert all(requirement.startswith("alpha") for requirement in first)
    assert second == ['beta>=3,<4 ; python_version >= "3.11"']
