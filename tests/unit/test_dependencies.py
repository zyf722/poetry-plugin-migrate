from __future__ import annotations

from email.parser import Parser
from itertools import product
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


class KeepPoetryDependenciesCommand(StubCommand):
    def confirm(self, question: str, default: bool = False) -> bool:
        if "Keeps dependencies" in question:
            return True
        return default


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


def test_unrepresentable_constraint_keeps_complete_dependency_model(
    tmp_path: Path,
) -> None:
    result, migrator = migrate(
        """\
[tool.poetry]
name = "dummy-union-project"
version = "1.0.0"
description = "Synthetic unrepresentable dependency"
authors = []

[tool.poetry.extras]
feature = ["dummy-union"]

[tool.poetry.dependencies]
python = ">=3.10"
dummy-safe = "^1.0"
dummy-union = { version = ">=1,<2 || >=3,<4", optional = true }
"""
    )

    project = require_table(result["project"], "project")
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    dependencies = require_table(
        tool_poetry["dependencies"], "tool.poetry.dependencies"
    )
    extras = require_table(tool_poetry["extras"], "tool.poetry.extras")

    assert "dependencies" not in project
    assert project["dynamic"] == ["dependencies"]
    assert dependencies["dummy-safe"] == "^1.0"
    assert dependencies["dummy-union"] == {
        "version": ">=1,<2 || >=3,<4",
        "optional": True,
    }
    assert extras["feature"] == ["dummy-union"]
    assert any("PEP 508 round-trip failed" in warning for warning in migrator.warnings)

    (tmp_path / "pyproject.toml").write_text(result.as_string())
    assert Factory().create_poetry(tmp_path).package.name == "dummy-union-project"


def test_existing_project_dependency_array_aborts_instead_of_changing_metadata() -> (
    None
):
    with pytest.raises(ValueError, match="Cannot safely migrate Poetry dependencies"):
        migrate(
            """\
[project]
dependencies = ["click>=8"]

[tool.poetry.dependencies]
python = "^3.10"
requests = "^2.32"
"""
        )


def test_empty_standard_dependency_containers_are_migration_placeholders() -> None:
    result, _ = migrate(
        """\
[project]
dependencies = []

[project.optional-dependencies]

[tool.poetry.extras]
feature = ["dummy-optional"]

[tool.poetry.dependencies]
python = ">=3.10"
dummy-runtime = "^1"
dummy-optional = { version = "^2", optional = true }
"""
    )

    project = require_table(result["project"], "project")
    optional = require_table(
        project["optional-dependencies"], "project.optional-dependencies"
    )
    assert project["dependencies"] == ["dummy-runtime>=1,<2"]
    assert optional["feature"] == ["dummy-optional>=2,<3"]


def test_empty_legacy_extras_do_not_conflict_with_existing_standard_extras() -> None:
    result, _ = migrate(
        """\
[project.optional-dependencies]
existing = ["dummy-existing>=1"]

[tool.poetry.extras]

[tool.poetry.dependencies]
python = ">=3.10"
dummy-runtime = "^2"
"""
    )

    project = require_table(result["project"], "project")
    optional = require_table(
        project["optional-dependencies"], "project.optional-dependencies"
    )
    tool = require_table(result["tool"], "tool")
    poetry = require_table(tool["poetry"], "tool.poetry")
    assert optional["existing"] == ["dummy-existing>=1"]
    assert project["dependencies"] == ["dummy-runtime>=2,<3"]
    assert "extras" not in poetry


def test_empty_standard_placeholders_are_removed_for_unsafe_poetry_model() -> None:
    result, migrator = migrate(
        """\
[project]
name = "dummy-placeholder"
version = "1.0.0"
dependencies = []

[project.optional-dependencies]

[tool.poetry.dependencies]
python = ">=3.10"
dummy-local = { path = "../dummy-local", optional = true }

[tool.poetry.extras]
feature = ["dummy-local"]
"""
    )

    project = require_table(result["project"], "project")
    tool = require_table(result["tool"], "tool")
    poetry = require_table(tool["poetry"], "tool.poetry")
    assert "dependencies" not in project
    assert "optional-dependencies" not in project
    assert project["dynamic"] == ["dependencies"]
    assert "dependencies" in poetry
    assert "extras" in poetry
    assert any("relative path" in warning for warning in migrator.warnings)


def test_empty_standard_placeholders_are_removed_when_user_keeps_poetry_model() -> None:
    migrator = Migrator(KeepPoetryDependenciesCommand(), skip=False, literal=False)
    result = migrator.run(
        parse(
            """\
[project]
name = "dummy-placeholder"
version = "1.0.0"
dependencies = []

[project.optional-dependencies]

[tool.poetry.dependencies]
python = ">=3.10"
dummy-extra = { version = "^1", optional = true }

[tool.poetry.extras]
feature = ["dummy-extra"]
"""
        )
    )

    project = require_table(result["project"], "project")
    assert "dependencies" not in project
    assert "optional-dependencies" not in project
    assert project["dynamic"] == ["dependencies"]


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


def test_shared_optional_dependency_is_rendered_for_every_extra() -> None:
    result, _ = migrate(
        """\
[tool.poetry.extras]
first = ["dummy-shared"]
second = ["dummy-shared"]

[tool.poetry.dependencies]
python = ">=3.10"
dummy-shared = { version = "^2.3", optional = true, extras = ["speed"] } # shared note
"""
    )

    project = require_table(result["project"], "project")
    optional = require_table(
        project["optional-dependencies"], "project.optional-dependencies"
    )
    expected = ["dummy-shared[speed]>=2.3,<3.0"]
    assert optional["first"] == expected
    assert optional["second"] == expected
    assert result.as_string().count("# shared note") == 1


def test_extra_dependency_names_are_matched_using_pep503_normalization() -> None:
    result, _ = migrate(
        """\
[tool.poetry.extras]
feature = ["dummy_shared"]

[tool.poetry.dependencies]
python = ">=3.10"
Dummy-Shared = { version = "^2.3", optional = true }
"""
    )

    project = require_table(result["project"], "project")
    optional = require_table(
        project["optional-dependencies"], "project.optional-dependencies"
    )
    assert optional["feature"] == ["Dummy-Shared>=2.3,<3.0"]


@pytest.mark.parametrize(
    "source, message",
    [
        (
            """\
[tool.poetry.extras]
feature_one = ["dummy"]
feature-one = ["dummy"]

[tool.poetry.dependencies]
python = ">=3.10"
dummy = { version = "^1", optional = true }
""",
            "Duplicate Poetry extra names after normalization",
        ),
        (
            """\
[tool.poetry.dependencies]
python = ">=3.10"
dummy_name = "^1"
dummy-name = "^2"
""",
            "Duplicate Poetry dependency names after normalization",
        ),
    ],
)
def test_normalized_name_collisions_abort(source: str, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        migrate(source)


@pytest.mark.parametrize(
    "dependency_lines, warning_fragment",
    [
        (
            'dummy = { version = "^1", optional = true }',
            "optional dependency is not referenced by any extra",
        ),
        (
            'dummy = "^1"\n\n[tool.poetry.extras]\nfeature = ["dummy"]',
            "dependency referenced by an extra is not optional",
        ),
    ],
)
def test_inconsistent_legacy_extra_models_are_preserved_as_a_whole(
    dependency_lines: str, warning_fragment: str
) -> None:
    result, migrator = migrate(
        f"""\
[tool.poetry.dependencies]
python = ">=3.10"
{dependency_lines}
"""
    )

    project = require_table(result["project"], "project")
    tool = require_table(result["tool"], "tool")
    poetry = require_table(tool["poetry"], "tool.poetry")
    legacy = require_table(poetry["dependencies"], "tool.poetry.dependencies")
    assert project["dynamic"] == ["dependencies"]
    assert "dummy" in legacy
    assert any(warning_fragment in warning for warning in migrator.warnings)


def test_existing_optional_dependencies_abort_legacy_extra_migration() -> None:
    with pytest.raises(ValueError, match=r"Cannot safely merge.*optional-dependencies"):
        migrate(
            """\
[project.optional-dependencies]
feature = ["dummy>=1"]

[tool.poetry.extras]
feature = ["dummy"]

[tool.poetry.dependencies]
python = ">=3.10"
dummy = { version = "^1", optional = true }
"""
        )


@pytest.mark.parametrize("constraint", [">=3.10 || <3.8", ">=3.10+local"])
def test_non_standard_python_constraint_remains_poetry_dynamic(
    constraint: str,
) -> None:
    result, migrator = migrate(
        f"""\
[tool.poetry.dependencies]
python = "{constraint}"
dummy = "^1"
"""
    )

    project = require_table(result["project"], "project")
    tool = require_table(result["tool"], "tool")
    poetry = require_table(tool["poetry"], "tool.poetry")
    legacy = require_table(poetry["dependencies"], "tool.poetry.dependencies")
    dynamic = require_array(project["dynamic"], "project.dynamic")
    assert "requires-python" not in project
    assert "requires-python" in dynamic
    assert legacy["python"] == constraint
    assert project["dependencies"] == ["dummy>=1,<2"]
    assert any("standard Requires-Python" in warning for warning in migrator.warnings)


def test_apostrophe_in_direct_url_is_preserved_when_pep508_rejects_it() -> None:
    migrator = Migrator(StubCommand(), skip=True, literal=True)
    result = migrator.run(
        parse(
            """\
[tool.poetry.dependencies]
python = ">=3.10"
dummy = { url = "https://example.invalid/owner's/dummy.whl" }
"""
        )
    )

    reparsed = parse(result.as_string())
    project = require_table(reparsed["project"], "project")
    tool = require_table(reparsed["tool"], "tool")
    poetry = require_table(tool["poetry"], "tool.poetry")
    legacy = require_table(poetry["dependencies"], "tool.poetry.dependencies")
    assert project["dynamic"] == ["dependencies"]
    assert legacy["dummy"] == {"url": "https://example.invalid/owner's/dummy.whl"}


def test_multi_constraint_order_is_preserved() -> None:
    result, _ = migrate(
        """\
[tool.poetry.dependencies]
python = ">=3.10"
dummy = [
    { version = "^1", platform = "win32" },
    { version = "^2", platform = "linux" },
    { version = "^3", python = ">=3.12" },
]
"""
    )

    project = require_table(result["project"], "project")
    dependencies = require_array(project["dependencies"], "project.dependencies")
    assert [str(value).split(">=", 1)[1][0] for value in dependencies] == [
        "1",
        "2",
        "3",
    ]


def test_multi_constraint_comments_stay_with_their_generated_requirements() -> None:
    result, migrator = migrate(
        """\
[tool.poetry.dependencies]
python = ">=3.10"
dummy = [
    # Windows branch
    { version = "^1", platform = "win32" }, #win
    { version = "^2", platform = "linux" }, ## Linux heading
]
"""
    )

    rendered = result.as_string()
    assert '# Windows branch\n    "dummy>=1,<2' in rendered
    assert '\\"win32\\"", #win' in rendered
    assert '\\"linux\\"", ## Linux heading' in rendered
    assert not any("Restored" in warning for warning in migrator.warnings)


def test_optional_multi_constraint_comments_stay_with_their_extra() -> None:
    result, migrator = migrate(
        """\
[tool.poetry.dependencies]
python = ">=3.10"
dummy = [
    # old runtime branch
    { version = "^1", python = "<3.12", optional = true }, #old
    { version = "^2", python = ">=3.12", optional = true }, ## new runtime
]

[tool.poetry.extras]
feature = ["dummy"]
"""
    )

    rendered = result.as_string()
    assert '# old runtime branch\n    "dummy>=1,<2' in rendered
    assert 'python_version < \\"3.12\\"", #old' in rendered
    assert 'python_version >= \\"3.12\\"", ## new runtime' in rendered
    assert not any("Restored" in warning for warning in migrator.warnings)


def test_python_only_legacy_table_leaves_an_explicit_empty_dependency_array() -> None:
    result, _ = migrate(
        """\
[tool.poetry]
name = "dummy-empty"
version = "1.0.0"

[tool.poetry.dependencies]
python = ">=3.10"
"""
    )

    project = require_table(result["project"], "project")
    assert project["dependencies"] == []
    assert Factory.validate(result.unwrap(), strict=True)["errors"] == []


def _requires_dist(wheel: Path) -> set[str]:
    with ZipFile(wheel) as archive:
        metadata_name = next(
            name for name in archive.namelist() if name.endswith(".dist-info/METADATA")
        )
        metadata = Parser().parsestr(archive.read(metadata_name).decode())
    return set(metadata.get_all("Requires-Dist", []))


def _requirement_semantics(
    requirements: set[str],
) -> dict[tuple[str, str, str], set[tuple[object, ...]]]:
    parsed = [Requirement(raw_requirement) for raw_requirement in requirements]
    result: dict[tuple[str, str, str], set[tuple[object, ...]]] = {}
    systems = (("win32", "Windows"), ("linux", "Linux"), ("darwin", "Darwin"))
    for extra, (sys_platform, platform_system), python_version in product(
        ("", "first", "second", "unrelated"), systems, ("3.10", "3.12")
    ):
        environment = {
            "extra": extra,
            "sys_platform": sys_platform,
            "platform_system": platform_system,
            "python_version": python_version,
            "python_full_version": f"{python_version}.0",
        }
        active: set[tuple[object, ...]] = set()
        for requirement in parsed:
            if requirement.marker and not requirement.marker.evaluate(environment):
                continue
            active.add(
                (
                    canonicalize_name(requirement.name),
                    tuple(sorted(requirement.extras)),
                    str(requirement.specifier),
                    requirement.url,
                )
            )
        result[(extra, sys_platform, python_version)] = active
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

[tool.poetry.extras]
first = ["dummy-shared"]
second = ["dummy-shared"]

[tool.poetry.dependencies]
python = ">=3.10"
dummy-runtime = "^2.0"
dummy-feature = { version = "~3.1", extras = ["speed"] }
dummy-marker = { version = ">=4,<5", markers = "sys_platform == 'win32'" }
dummy-url = { url = "https://example.invalid/dummy_url-5.0-py3-none-any.whl" }
dummy-shared = { version = "^6.0", optional = true }
"""
    pyproject = project / "pyproject.toml"
    pyproject.write_text(source)

    before_poetry = Factory().create_poetry(project)
    before_wheel = WheelBuilder(before_poetry).build(tmp_path / "before-dist")

    result, migrator = migrate(source)
    pyproject.write_text(result.as_string())
    after_poetry = Factory().create_poetry(project)
    after_wheel = WheelBuilder(after_poetry).build(tmp_path / "after-dist")

    assert _requirement_semantics(
        _requires_dist(after_wheel)
    ) == _requirement_semantics(_requires_dist(before_wheel))
    project_table = require_table(result["project"], "project")
    project_dependencies = require_array(
        project_table["dependencies"], "project.dependencies"
    )
    assert (
        "dummy-url @ https://example.invalid/dummy_url-5.0-py3-none-any.whl"
        in project_dependencies
    )
    optional = require_table(
        project_table["optional-dependencies"], "project.optional-dependencies"
    )
    assert optional["first"] == ["dummy-shared>=6.0,<7.0"]
    assert optional["second"] == ["dummy-shared>=6.0,<7.0"]
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    legacy_dependencies = require_table(
        tool_poetry["dependencies"], "tool.poetry.dependencies"
    )
    assert "dummy-url" not in legacy_dependencies
    assert not any(
        "PEP 508 round-trip failed" in warning for warning in migrator.warnings
    )
