from __future__ import annotations

from pathlib import Path

import pytest
from poetry.factory import Factory
from tomlkit import TOMLDocument, parse

from poetry_plugin_migrate.migrator import Migrator
from poetry_plugin_migrate.toml import (
    reorder_standard_tables,
    require_array,
    require_item,
    require_table,
)


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


class CanonicalLayoutCommand(StubCommand):
    def __init__(self) -> None:
        self.confirmations: list[str] = []

    def confirm(self, question: str, default: bool = False) -> bool:
        self.confirmations.append(question)
        if "canonical layout" in question:
            return True
        return default


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


def test_standard_metadata_containers_remain_authoritative() -> None:
    source = """\
[project]
name = "standard-name"
version = "2.0.0"
readme = "STANDARD.md"
classifiers = ["Topic :: Standard"]
authors = [{ name = "Standard Author" }]
maintainers = [{ name = "Standard Maintainer" }]

[project.urls]
Homepage = "https://standard.invalid"

[project.scripts]
standard = "dummy:standard"

[project.entry-points."dummy.plugins"]
standard = "dummy:plugin"

[tool.poetry]
name = "legacy-name"
version = "1.0.0"
readme = "LEGACY.md"
classifiers = ["Topic :: Legacy"]
authors = ["Legacy Author <legacy@example.invalid>"]
maintainers = ["Legacy Maintainer"]
homepage = "https://legacy.invalid"

[tool.poetry.urls]
Tracker = "https://legacy.invalid/issues"

[tool.poetry.scripts]
legacy = "dummy:legacy"

[tool.poetry.plugins."dummy.plugins"]
legacy = "dummy:plugin"
"""

    result, migrator = migrate(source)
    project = require_table(result["project"], "project")
    tool = require_table(result["tool"], "tool")
    poetry = require_table(tool["poetry"], "tool.poetry")

    assert project["name"] == "standard-name"
    assert project["version"] == "2.0.0"
    assert project["readme"] == "STANDARD.md"
    assert project["classifiers"] == ["Topic :: Standard"]
    assert project["authors"] == [{"name": "Standard Author"}]
    assert project["maintainers"] == [{"name": "Standard Maintainer"}]
    assert "readme" in poetry
    assert "classifiers" in poetry
    assert "authors" in poetry
    assert "maintainers" in poetry
    assert "homepage" in poetry and "urls" in poetry
    assert "scripts" in poetry and "plugins" in poetry
    assert any("effective project URLs" in warning for warning in migrator.warnings)


def test_migration_removes_only_new_static_dynamic_conflicts() -> None:
    result, migrator = migrate(
        """\
[project]
name = "dummy"
version = "1.0.0"
dynamic = ["description", "readme"]

[tool.poetry]
description = "migrated static value"
"""
    )

    project = require_table(result["project"], "project")
    assert project["dynamic"] == ["readme"]
    assert (
        sum("from [project.dynamic]" in warning for warning in migrator.warnings) == 1
    )


def test_preexisting_static_dynamic_conflict_is_not_silently_repaired() -> None:
    source = """\
[project]
name = "dummy"
version = "1.0.0"
dynamic = ["name"]

[tool.poetry]
packages = [{ include = "dummy" }]
"""

    result, migrator = migrate(source)

    assert result.as_string() == source
    assert not any("from [project.dynamic]" in warning for warning in migrator.warnings)


def test_non_package_project_without_metadata_still_migrates_groups() -> None:
    result, migrator = migrate(
        """\
[tool.poetry]
package-mode = false

[tool.poetry.group.dev.dependencies]
dummy-dev = "^1"
"""
    )

    assert "project" not in result
    groups = require_table(result["dependency-groups"], "dependency-groups")
    assert groups["dev"] == ["dummy-dev>=1,<2"]
    assert any(
        "PEP 621 [project] migration was skipped" in w for w in migrator.warnings
    )


def test_file_only_scripts_do_not_create_empty_project_scripts() -> None:
    result, _ = migrate(
        """\
[tool.poetry]
name = "dummy"
version = "1.0.0"

[tool.poetry.scripts]
binary = { reference = "dummy.exe", type = "file" }
"""
    )

    project = require_table(result["project"], "project")
    tool = require_table(result["tool"], "tool")
    poetry = require_table(tool["poetry"], "tool.poetry")
    assert "scripts" not in project
    assert "scripts" in poetry


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


@pytest.mark.parametrize(
    ("license_expression", "expected"),
    [
        ("MIT", "MIT"),
        ("MIT OR Apache-2.0", "MIT OR Apache-2.0"),
        ("mit or apache-2.0", "MIT OR Apache-2.0"),
    ],
)
def test_valid_spdx_license_moves_to_project(
    license_expression: str, expected: str
) -> None:
    result, migrator = migrate(
        f'''\
[tool.poetry]
name = "dummy-license"
version = "1.0.0"
license = "{license_expression}" # license note
'''
    )

    project = require_table(result["project"], "project")
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    license_item = require_item(project["license"], "project.license")
    assert str(license_item) == expected
    assert "license note" in license_item.trivia.comment
    assert "license" not in tool_poetry
    assert not any("SPDX" in warning for warning in migrator.warnings)


def test_legacy_license_text_is_kept_without_inferring_spdx(
    tmp_path: Path,
) -> None:
    source = """\
[tool.poetry]
name = "dummy-license"
version = "1.0.0"
description = "Dummy legacy license project"
authors = []
license = "MIT License"
"""
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(source)
    before = Factory().create_poetry(tmp_path).package.license

    result, migrator = migrate(source)
    pyproject.write_text(result.as_string())
    after = Factory().create_poetry(tmp_path).package.license

    project = require_table(result["project"], "project")
    tool = require_table(result["tool"], "tool")
    tool_poetry = require_table(tool["poetry"], "tool.poetry")
    assert "license" not in project
    assert project["dynamic"] == ["license"]
    assert tool_poetry["license"] == "MIT License"
    assert after == before
    assert any(
        "not a valid SPDX expression" in warning for warning in migrator.warnings
    )


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


def test_split_poetry_tables_are_not_consolidated_without_a_real_edit() -> None:
    source = """\
[project]
name = "already-modern"
version = "1.0.0"

[tool.poetry]
packages = [{ include = "dummy" }]

[metadata]
note = "keeps the physical split"

[tool.poetry.group.dev]
optional = true
"""

    result = Migrator(StubCommand(), skip=False, literal=False).run(parse(source))

    assert result.as_string() == source


def test_canonical_layout_is_opt_in_and_preserves_table_contents() -> None:
    source = """\
# document header

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"
# comment retained by tomlkit with build-system

[metadata]
dummy = "untouched"

[tool.poetry]
name = "canonical-layout"
version = "1.0.0"

[tool.poetry.dependencies]
python = ">=3.10"
dummy-runtime = "^2.0"

[tool.poetry.group.test]
include-groups = ["lint"]

[tool.poetry.group.test.dependencies]
dummy-test = "^3.0"

[tool.poetry.group.lint.dependencies]
dummy-lint = "^4.0"
    """
    default_result, _ = migrate(source)
    command = CanonicalLayoutCommand()
    canonical_result = Migrator(command, skip=False, literal=False).run(parse(source))

    default_output = default_result.as_string()
    canonical_output = canonical_result.as_string()
    assert default_output.index("[build-system]") < default_output.index("[project]")
    assert canonical_output.startswith("# document header\n\n[project]")
    assert canonical_output.index("[project]") < canonical_output.index(
        "[dependency-groups]"
    )
    assert canonical_output.index("[dependency-groups]") < canonical_output.index(
        "[tool.poetry]"
    )
    assert canonical_output.index("[tool.poetry]") < canonical_output.index(
        "[metadata]"
    )
    assert canonical_output.index("[metadata]") < canonical_output.index(
        "[build-system]"
    )
    assert "# comment retained by tomlkit with build-system" in canonical_output

    canonical_groups = require_table(
        canonical_result["dependency-groups"], "dependency-groups"
    )
    test_group = require_array(canonical_groups["test"], "dependency-groups.test")
    include = require_table(test_group[0], "dependency-groups.test[0]")
    assert include["include-group"] == "lint"
    assert test_group[1] == "dummy-test>=3.0,<4.0"
    assert canonical_groups["lint"] == ["dummy-lint>=4.0,<5.0"]
    assert parse(canonical_output).unwrap() == canonical_result.unwrap()
    assert "canonical layout" in command.confirmations[-1]


def test_canonical_layout_is_idempotent_and_keeps_existing_project_fields() -> None:
    source = """\
[tool.poetry]
packages = [{ include = "dummy" }]

[project]
z-custom = "first"
name = "already-modern"
version = "1.0.0"
dependencies = [
    "zeta>=1",
    "alpha>=2",
]

[build-system]
requires = ["poetry-core>=2"]
build-backend = "poetry.core.masonry.api"
"""
    migrator = Migrator(CanonicalLayoutCommand(), skip=False, literal=False)
    first = migrator.run(parse(source))
    second = Migrator(CanonicalLayoutCommand(), skip=False, literal=False).run(
        parse(first.as_string())
    )

    project = require_table(first["project"], "project")
    assert list(project.keys()) == ["z-custom", "name", "version", "dependencies"]
    assert project["dependencies"] == ["zeta>=1", "alpha>=2"]
    assert first.as_string() == second.as_string()


def test_canonical_layout_keeps_interleaved_tool_blocks_and_comments() -> None:
    source = """\
[tool.poetry]
packages = [{ include = "dummy" }]

[dependency-groups]
existing = ["dummy-existing>=1"]

# dependency-groups trailing note
[tool.ruff]
line-length = 100

[build-system]
requires = ["poetry-core>=2"]
build-backend = "poetry.core.masonry.api"
"""
    result = Migrator(CanonicalLayoutCommand(), skip=False, literal=False).run(
        parse(source)
    )
    output = result.as_string()

    assert output.index("[project]") < output.index("[dependency-groups]")
    assert output.index("[dependency-groups]") < output.index("[tool.poetry]")
    assert output.index("[dependency-groups]") < output.index(
        "# dependency-groups trailing note"
    )
    assert output.index("# dependency-groups trailing note") < output.index(
        "[tool.poetry]"
    )
    assert output.index("[tool.poetry]") < output.index("[tool.ruff]")
    assert output.index("[tool.ruff]") < output.index("[build-system]")
    assert output.count("# dependency-groups trailing note") == 1

    tool = require_table(result["tool"], "tool")
    poetry = require_table(tool["poetry"], "tool.poetry")
    ruff = require_table(tool["ruff"], "tool.ruff")
    groups = require_table(result["dependency-groups"], "dependency-groups")
    assert poetry["packages"] == [{"include": "dummy"}]
    assert ruff["line-length"] == 100
    assert groups["existing"] == ["dummy-existing>=1"]
    assert parse(output).unwrap() == result.unwrap()


def test_canonical_layout_treats_array_of_tables_as_an_independent_block() -> None:
    source = """\
[build-system]
requires = ["poetry-core>=2"]
build-backend = "poetry.core.masonry.api"

[[custom.targets]]
name = "first"

[[custom.targets]]
name = "second"

[tool.poetry]
name = "array-of-tables"
version = "1.0.0"
"""
    result = Migrator(CanonicalLayoutCommand(), skip=False, literal=False).run(
        parse(source)
    )
    output = result.as_string()

    assert output.index("[project]") < output.index("[tool.poetry]")
    assert output.index("[tool.poetry]") < output.index("[[custom.targets]]")
    assert output.index("[[custom.targets]]") < output.index("[build-system]")
    assert output.index('name = "first"') < output.index('name = "second"')
    assert parse(output).unwrap() == result.unwrap()


def test_canonical_layout_places_all_poetry_tables_before_other_tools() -> None:
    source = """\
# document header
[tool.ruff]
line-length = 100
# ruff note

[metadata]
dummy = "untouched"

[tool.poetry]
packages = [{ include = "dummy" }]
# poetry main note

[tool.pytest.ini_options]
addopts = "-q"
# pytest note

[other]
enabled = true

[tool.poetry.dependencies]
python = ">=3.10"
dummy-runtime = "^2.0"
# poetry dependencies note

[tool.ruff.lint]
select = ["E"]
# ruff lint note

[build-system]
requires = ["poetry-core>=2"]
build-backend = "poetry.core.masonry.api"
"""
    command = CanonicalLayoutCommand()
    result = Migrator(command, skip=False, literal=False).run(parse(source))
    output = result.as_string()

    poetry = output.index("[tool.poetry]")
    poetry_dependencies = output.index("[tool.poetry.dependencies]")
    ruff = output.index("[tool.ruff]")
    pytest_options = output.index("[tool.pytest.ini_options]")
    ruff_lint = output.index("[tool.ruff.lint]")
    assert poetry < poetry_dependencies < ruff < pytest_options < ruff_lint
    for note in (
        "ruff note",
        "poetry main note",
        "pytest note",
        "poetry dependencies note",
        "ruff lint note",
    ):
        assert output.count(note) == 1
    assert "\n\n[tool.ruff]" in output
    assert parse(output).unwrap() == result.unwrap()

    second = Migrator(CanonicalLayoutCommand(), skip=False, literal=False).run(
        parse(output)
    )
    assert second.as_string() == output


def test_canonical_layout_preserves_explicit_tool_namespace_preamble() -> None:
    source = """\
[tool]
owner = "dummy"
# namespace note

[tool.ruff]
line-length = 100

[tool.poetry]
packages = [{ include = "dummy" }]

[build-system]
requires = ["poetry-core>=2"]
build-backend = "poetry.core.masonry.api"
"""
    original = parse(source)
    result = reorder_standard_tables(original)
    output = result.as_string()

    assert output.startswith('[tool]\nowner = "dummy"\n# namespace note\n')
    assert output.index("[tool.poetry]") < output.index("[tool.ruff]")
    assert output.count("# namespace note") == 1
    assert result.unwrap() == original.unwrap()
    assert reorder_standard_tables(parse(output)).as_string() == output


def test_canonical_layout_places_poetry_before_tool_array_of_tables() -> None:
    source = """\
[[tool.custom]]
name = "first"

[[tool.custom]]
name = "second"

[tool.poetry]
packages = [{ include = "dummy" }]
"""
    original = parse(source)
    result = reorder_standard_tables(original)
    output = result.as_string()

    assert output.index("[tool.poetry]") < output.index("[[tool.custom]]")
    assert output.index('name = "first"') < output.index('name = "second"')
    assert "\n\n[[tool.custom]]" in output
    assert result.unwrap() == original.unwrap()
    assert reorder_standard_tables(parse(output)).as_string() == output


def test_default_layout_does_not_prioritize_poetry_tables() -> None:
    source = """\
[tool.ruff]
line-length = 100

[tool.poetry]
packages = [{ include = "dummy" }]

[tool.pytest.ini_options]
addopts = "-q"
"""
    result, _ = migrate(source)
    output = result.as_string()

    assert output.index("[tool.ruff]") < output.index("[tool.poetry]")
    assert output.index("[tool.poetry]") < output.index("[tool.pytest.ini_options]")
