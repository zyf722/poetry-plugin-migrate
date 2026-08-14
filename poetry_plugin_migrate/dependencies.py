from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, TypeAlias

from packaging.specifiers import InvalidSpecifier, SpecifierSet
from packaging.utils import canonicalize_name
from tomlkit import TOMLDocument
from tomlkit.items import Array, InlineTable, Item, String

from poetry_plugin_migrate.requirements import (
    UnrepresentableRequirementError,
    render_pep508_requirement,
)
from poetry_plugin_migrate.toml import (
    TomlTable,
    append_array_value,
    extend_array_preserving_comments,
    is_table,
    make_string,
    require_array,
    require_item,
    require_table,
)

if TYPE_CHECKING:
    from poetry.core.packages.dependency import Dependency

    from poetry_plugin_migrate.migrator import Migrator


DependencySpec: TypeAlias = str | Mapping[str, object]


class DependencyMigrator:
    """Handles migration of [tool.poetry.dependencies] and extras."""

    def __init__(
        self, migrator: Migrator, tool_poetry: TomlTable, project: TomlTable
    ) -> None:
        self.migrator = migrator
        self.tool_poetry = tool_poetry
        self.project = project
        self.deps = require_table(
            tool_poetry["dependencies"], "tool.poetry.dependencies"
        )
        project_dependencies = project.get("dependencies")
        self.project_dependencies_preexisting = (
            project_dependencies is not None
            and len(require_array(project_dependencies, "project.dependencies")) > 0
        )
        project_optional = project.get("optional-dependencies")
        self.project_optional_preexisting = (
            project_optional is not None
            and len(require_table(project_optional, "project.optional-dependencies"))
            > 0
        )
        legacy_extras = tool_poetry.get("extras")
        self.legacy_extras_nonempty = is_table(legacy_extras) and len(legacy_extras) > 0

    def run(self) -> None:
        self.keep_version_brackets = self.migrator._keep_pep508_version_brackets()
        self._migrate_requires_python()

        non_python = [name for name in self.deps if name != "python"]
        if not non_python:
            if len(self.deps) == 0:
                del self.tool_poetry["dependencies"]
            elif "dependencies" not in self.project:
                from tomlkit import array

                empty_dependencies = array()
                empty_dependencies.multiline(True)
                self.project["dependencies"] = empty_dependencies
            return
        if self.project_dependencies_preexisting and non_python:
            raise ValueError(
                "Cannot safely migrate Poetry dependencies by merging "
                "[tool.poetry.dependencies] into an existing "
                "[project.dependencies] array. Poetry treats the standardized array "
                "as authoritative, so adding legacy-only entries could change wheel "
                "metadata. Resolve the declarations manually."
            )
        if self.project_optional_preexisting and self.legacy_extras_nonempty:
            raise ValueError(
                "Cannot safely merge [tool.poetry.extras] into an existing "
                "[project.optional-dependencies] table. Extra names are normalized "
                "and Poetry treats the standardized table as authoritative. Resolve "
                "the declarations manually."
            )

        unsafe_dependencies = self._unsafe_main_dependencies()
        if unsafe_dependencies:
            self._keep_unsafe_dependencies(unsafe_dependencies)
            return

        if self._keep_dependencies_in_poetry():
            return

        self._migrate_optional_dependencies()
        self._migrate_main_dependencies()

    def _keep_dependencies_in_poetry(self) -> bool:
        if not self.migrator._prompt(
            "Keeps dependencies in <b>[tool.poetry]</b>?",
            additional_info=(
                "<b>[tool.poetry.dependencies]</b> found. "
                "`dependencies` will be added to <b>[project.dynamic]</b> "
                "if you want to keep it in <b>[tool.poetry]</b>. "
            ),
        ):
            return False
        self._remove_empty_standard_dependency_placeholders()
        self.migrator._add_dynamic(self.project, "dependencies")
        return True

    def _remove_empty_standard_dependency_placeholders(self) -> None:
        """Remove empty standard containers before using the Poetry model.

        Empty standard dependency containers are accepted as migration
        placeholders. If migration falls back to the complete Poetry model,
        leaving those placeholders in place would make them authoritative and
        conflict with ``project.dynamic`` or suppress legacy extras.
        """
        project_dependencies = self.project.get("dependencies")
        if isinstance(project_dependencies, Array) and len(project_dependencies) == 0:
            del self.project["dependencies"]

        project_optional = self.project.get("optional-dependencies")
        if (
            self.legacy_extras_nonempty
            and is_table(project_optional)
            and len(project_optional) == 0
        ):
            del self.project["optional-dependencies"]

    def _dependency_name_map(self) -> dict[str, str]:
        result: dict[str, str] = {}
        for name in self.deps:
            if name == "python":
                continue
            normalized = canonicalize_name(str(name))
            if normalized in result and result[normalized] != str(name):
                raise ValueError(
                    "Duplicate Poetry dependency names after normalization: "
                    f"{result[normalized]!r} and {str(name)!r}."
                )
            result[normalized] = str(name)
        return result

    def _extra_references(self) -> dict[str, set[str]]:
        extras = self.tool_poetry.get("extras")
        if extras is None:
            return {}
        extras_table = require_table(extras, "tool.poetry.extras")
        references: dict[str, set[str]] = {}
        normalized_extra_names: dict[str, str] = {}
        dependency_names = self._dependency_name_map()

        for extra_name, raw_members in extras_table.items():
            normalized_extra = canonicalize_name(str(extra_name))
            previous_extra = normalized_extra_names.get(normalized_extra)
            if previous_extra is not None and previous_extra != str(extra_name):
                raise ValueError(
                    "Duplicate Poetry extra names after normalization: "
                    f"{previous_extra!r} and {str(extra_name)!r}."
                )
            normalized_extra_names[normalized_extra] = str(extra_name)

            members = require_array(raw_members, f"tool.poetry.extras.{extra_name}")
            for member in members:
                if not isinstance(member, str):
                    raise TypeError(
                        f"[tool.poetry.extras.{extra_name}] entries must be strings"
                    )
                normalized_member = canonicalize_name(member)
                dependency_name = dependency_names.get(normalized_member)
                if dependency_name is None:
                    references.setdefault(normalized_member, set()).add(
                        f"missing dependency referenced by extra {extra_name}"
                    )
                    continue
                references.setdefault(normalized_member, set()).add(str(extra_name))
        return references

    def _unsafe_main_dependencies(self) -> dict[str, set[str]]:
        """Return dependencies that cannot be represented safely in PEP 508."""
        from poetry.core.factory import Factory
        from poetry.core.packages.path_dependency import PathDependency

        unsafe: dict[str, set[str]] = {}
        extra_references = self._extra_references()
        for package_name, raw_constraint in self.deps.items():
            if package_name == "python":
                continue
            constraints: list[object] = (
                list(raw_constraint)
                if isinstance(raw_constraint, Array)
                else [raw_constraint]
            )
            for constraint in constraints:
                dependency = Factory.create_dependency(
                    str(package_name),
                    deepcopy(self._dependency_spec(constraint)),
                )
                try:
                    render_pep508_requirement(
                        dependency,
                        keep_version_brackets=self.keep_version_brackets,
                    )
                except UnrepresentableRequirementError:
                    unsafe.setdefault(str(package_name), set()).add(
                        "PEP 508 round-trip failed"
                    )
                if (
                    isinstance(dependency, PathDependency)
                    and not dependency.path.is_absolute()
                ):
                    unsafe.setdefault(str(package_name), set()).add("relative path")

                remaining = self._without_pep508_fields(
                    constraint, extra_fields=["optional"]
                )
                if is_table(remaining):
                    fields = {str(field) for field in remaining}
                    if fields:
                        unsafe.setdefault(str(package_name), set()).update(fields)

                normalized_dependency_name = canonicalize_name(str(package_name))
                referenced = normalized_dependency_name in extra_references
                if dependency.is_optional() and not referenced:
                    unsafe.setdefault(str(package_name), set()).add(
                        "optional dependency is not referenced by any extra"
                    )
                if referenced and not dependency.is_optional():
                    unsafe.setdefault(str(package_name), set()).add(
                        "dependency referenced by an extra is not optional"
                    )

        dependency_names = self._dependency_name_map()
        for missing_name, reasons in extra_references.items():
            if missing_name not in dependency_names:
                unsafe.setdefault(missing_name, set()).update(reasons)
        return unsafe

    def _keep_unsafe_dependencies(
        self, unsafe_dependencies: dict[str, set[str]]
    ) -> None:
        """Keep the complete Poetry dependency model when migration is lossy."""
        dependency_list = "; ".join(
            f"{name} ({', '.join(sorted(reasons))})"
            for name, reasons in sorted(unsafe_dependencies.items())
        )
        if self.project_dependencies_preexisting:
            raise ValueError(
                "Cannot safely migrate Poetry dependencies because dependencies "
                f"with Poetry-only semantics ({dependency_list}) coexist with "
                "[project.dependencies]. Remove the conflict or migrate these "
                "dependencies manually."
            )

        self._remove_empty_standard_dependency_placeholders()
        self.migrator.warnings.append(
            f"Dependencies {dependency_list} use semantics that cannot be represented "
            "completely in PEP 508 project metadata. All dependencies and extras "
            "were kept in [tool.poetry] to preserve dependency semantics."
        )
        self.migrator._add_dynamic(self.project, "dependencies")

    # ------------------------------------------------------------------
    # Step 2: requires-python
    # ------------------------------------------------------------------

    def _migrate_requires_python(self) -> None:
        """Handle migration of the python version constraint."""
        from poetry.core.constraints.version import parse_constraint

        if "python" not in self.deps or "requires-python" in self.project:
            return

        choices = [
            "Move to <b>[project.requires-python]</b>",
            "Add `requires-python` to <b>[project.dynamic]</b>",
            "Copy value to <b>[project.requires-python]</b>",
            "No migration and keep it as-is",
        ]
        migrate_python = self.migrator._choice(
            "How to migrate <b>[tool.poetry.dependencies.python]</b>?",
            choices,
            default=2,
        )
        if migrate_python in (choices[0], choices[2]):
            python_value = self.deps["python"]
            if not isinstance(python_value, str):
                raise TypeError("[tool.poetry.dependencies.python] must be a string")
            python_constraint = parse_constraint(python_value)
            standard_constraint = str(python_constraint)
            try:
                SpecifierSet(standard_constraint)
            except InvalidSpecifier:
                self.migrator.warnings.append(
                    f"[tool.poetry.dependencies.python] value {python_value!r} "
                    "cannot be represented as a standard Requires-Python "
                    "specifier. It was kept and [project.requires-python] was "
                    "marked dynamic."
                )
                self.migrator._add_dynamic(self.project, "requires-python")
                return
            self.project["requires-python"] = make_string(
                standard_constraint, literal=self.migrator.literal
            )
            if migrate_python == choices[0]:
                del self.deps["python"]

        elif migrate_python == choices[1]:
            self.migrator._add_dynamic(self.project, "requires-python")

    # ------------------------------------------------------------------
    # Step 3: Optional dependencies (extras)
    # ------------------------------------------------------------------

    def _migrate_optional_dependencies(self) -> None:
        """Transform [tool.poetry.extras] into [project.optional-dependencies]."""
        from poetry.core.factory import Factory
        from tomlkit import array, table

        if "extras" not in self.tool_poetry:
            return

        if "optional-dependencies" not in self.project:
            self.project["optional-dependencies"] = table()
        optional_dependencies = require_table(
            self.project["optional-dependencies"], "project.optional-dependencies"
        )

        dependency_names = self._dependency_name_map()
        extras = require_table(self.tool_poetry["extras"], "tool.poetry.extras")
        comments_emitted: set[str] = set()
        for extra_name, raw_members in extras.items():
            members = require_array(raw_members, f"tool.poetry.extras.{extra_name}")
            converted = array()
            converted.multiline(True)
            for member in members:
                if not isinstance(member, str):
                    raise TypeError(
                        f"[tool.poetry.extras.{extra_name}] entries must be strings"
                    )
                normalized_dependency_name = canonicalize_name(member)
                dependency_name = dependency_names[normalized_dependency_name]
                raw_constraint = self.deps[dependency_name]
                constraints = (
                    list(raw_constraint)
                    if isinstance(raw_constraint, Array)
                    else [raw_constraint]
                )
                replacements: list[Item] = []
                for constraint in constraints:
                    dependency = Factory.create_dependency(
                        dependency_name,
                        self._dependency_spec(deepcopy(constraint)),
                    )
                    replacements.append(self._pep508_string(dependency, constraint))
                if normalized_dependency_name in comments_emitted:
                    for replacement in replacements:
                        converted.add_line(replacement)
                elif isinstance(raw_constraint, Array):
                    extend_array_preserving_comments(
                        converted, raw_constraint, replacements
                    )
                else:
                    append_array_value(
                        converted,
                        replacements[0],
                        require_item(raw_constraint, "dependency constraint"),
                    )
                comments_emitted.add(normalized_dependency_name)
            optional_dependencies[extra_name] = converted

        del self.tool_poetry["extras"]

    # ------------------------------------------------------------------
    # Step 4: Main dependencies
    # ------------------------------------------------------------------

    def _migrate_main_dependencies(self) -> None:
        """Migrate main dependencies to [project.dependencies] or keep dynamic."""
        from poetry.core.factory import Factory
        from tomlkit import array

        if "dependencies" not in self.project:
            self.project["dependencies"] = array()
        project_deps = require_array(
            self.project["dependencies"], "project.dependencies"
        )
        project_deps.multiline(True)

        for dependency_name, raw_constraint in tuple(self.deps.items()):
            if dependency_name == "python":
                continue
            constraints = (
                list(raw_constraint)
                if isinstance(raw_constraint, Array)
                else [raw_constraint]
            )
            replacements: list[Item] = []
            for constraint in constraints:
                dependency = Factory.create_dependency(
                    str(dependency_name),
                    self._dependency_spec(deepcopy(constraint)),
                )
                if not dependency.is_optional():
                    replacements.append(self._pep508_string(dependency, constraint))
            if not replacements:
                continue
            if isinstance(raw_constraint, Array):
                extend_array_preserving_comments(
                    project_deps, raw_constraint, replacements
                )
            else:
                append_array_value(
                    project_deps,
                    replacements[0],
                    require_item(raw_constraint, "dependency constraint"),
                )
        # Replacing the complete nested table avoids tomlkit's stale index bug
        # for split declarations such as [tool.poetry.dependencies.foo].
        python_constraint = self.deps.get("python")
        del self.tool_poetry["dependencies"]
        if python_constraint is not None:
            from tomlkit import table

            remaining = table()
            remaining["python"] = deepcopy(python_constraint)
            self.tool_poetry["dependencies"] = remaining

    # ------------------------------------------------------------------
    # Utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _dependency_spec(value: object) -> DependencySpec:
        """Narrow a TOML dependency value to Poetry's accepted input shape."""
        if isinstance(value, str):
            return value
        if is_table(value):
            return value
        raise TypeError(
            "Dependency constraints must be strings or tables, "
            f"got {type(value).__name__}"
        )

    @staticmethod
    def _without_pep508_fields(
        constraint: object,
        extra_fields: list[str] | None = None,
        include_markers: bool = True,
    ) -> object:
        """Return Poetry-only fields not representable in the PEP 508 string.

        Rebuild the TOML table instead of popping keys in place. tomlkit 0.15.0
        can retain separator tokens after removing inline-table entries, yielding
        invalid output such as ``, , python = ...``.
        """
        if not is_table(constraint):
            return constraint
        fields = list(extra_fields) if extra_fields else []
        fields.extend(
            (
                "version",
                "git",
                "branch",
                "tag",
                "rev",
                "file",
                "path",
                "url",
                "subdirectory",
            )
        )
        if include_markers:
            fields.extend(("python", "platform", "markers", "extras"))
        from tomlkit import inline_table, table

        result = inline_table() if isinstance(constraint, InlineTable) else table()
        for field, value in constraint.items():
            if field not in fields:
                result[field] = deepcopy(value)
        return result

    def _pep508_string(self, dependency: Dependency, source: object) -> String:
        """Create a PEP 508 string while retaining source-item trivia."""
        result = make_string(
            render_pep508_requirement(
                dependency,
                keep_version_brackets=self.keep_version_brackets,
            ),
            literal=self.migrator.literal,
        )
        source_item = require_item(source, "dependency constraint")
        result.trivia.indent = deepcopy(source_item.trivia.indent)
        result.trivia.trail = deepcopy(source_item.trivia.trail)
        return result


class DependencyGroupMigrator:
    """Migrate Poetry dependency groups to the PEP 735 table.

    Poetry-specific group metadata such as ``optional = true`` remains under
    ``[tool.poetry.group.<name>]``. A group is left untouched when one of its
    dependencies cannot be represented without losing Poetry-only fields.
    """

    def __init__(
        self,
        migrator: Migrator,
        document: TOMLDocument,
        tool_poetry: TomlTable,
    ) -> None:
        self.migrator = migrator
        self.document = document
        self.tool_poetry = tool_poetry

    def run(self) -> None:
        from tomlkit import table

        poetry_groups = self.tool_poetry.get("group")
        legacy_dev = self.tool_poetry.get("dev-dependencies")
        if not is_table(poetry_groups) and not is_table(legacy_dev):
            return

        dependency_groups = self.document.get("dependency-groups")
        created_dependency_groups = dependency_groups is None
        if dependency_groups is None:
            dependency_groups = table()
            self.document["dependency-groups"] = dependency_groups
        elif not is_table(dependency_groups):
            self.migrator.warnings.append(
                "[dependency-groups] is not a table. Poetry dependency groups were kept unchanged."
            )
            return

        if is_table(legacy_dev):
            self._migrate_legacy_dev(dependency_groups, legacy_dev)

        if not is_table(poetry_groups):
            if created_dependency_groups and len(dependency_groups) == 0:
                del self.document["dependency-groups"]
            return

        fully_migrated: list[str] = []
        partially_migrated: list[str] = []
        original_group_names = tuple(poetry_groups.keys())

        for group_name in original_group_names:
            group = poetry_groups[group_name]
            if not is_table(group):
                self.migrator.warnings.append(
                    f"[tool.poetry.group.{group_name}] is not a table and was skipped."
                )
                continue
            existing_group = self._matching_group_name(
                dependency_groups, str(group_name)
            )
            if existing_group is not None:
                self.migrator.warnings.append(
                    f"[dependency-groups.{existing_group}] already exists or has an equivalent normalized name. "
                    f"[tool.poetry.group.{group_name}] was kept for review."
                )
                continue

            converted = self._convert_group(group_name, group)
            if converted is None:
                continue
            dependencies, consumed_keys = converted
            dependency_groups[group_name] = dependencies

            remaining_keys = set(group.keys()) - consumed_keys
            if len(remaining_keys) == 0:
                fully_migrated.append(group_name)
            else:
                partially_migrated.append(group_name)

        if len(fully_migrated) == len(original_group_names):
            # Avoid emptying every nested table before deleting its parent;
            # this is important for tomlkit's table index integrity.
            del self.tool_poetry["group"]
            return

        for group_name in fully_migrated:
            del poetry_groups[group_name]
        for group_name in partially_migrated:
            group = require_table(
                poetry_groups[group_name], f"tool.poetry.group.{group_name}"
            )
            group.pop("dependencies", None)
            group.pop("include-groups", None)

        if created_dependency_groups and len(dependency_groups) == 0:
            del self.document["dependency-groups"]

    def _migrate_legacy_dev(
        self, dependency_groups: TomlTable, legacy_dev: TomlTable
    ) -> None:
        if self._matching_group_name(dependency_groups, "dev") is not None or (
            is_table(self.tool_poetry.get("group"))
            and self._matching_group_name(
                require_table(self.tool_poetry["group"], "tool.poetry.group"), "dev"
            )
            is not None
        ):
            self.migrator.warnings.append(
                "[tool.poetry.dev-dependencies] conflicts with an existing dev group and was kept."
            )
            return

        dependencies = self._convert_dependencies(
            "tool.poetry.dev-dependencies", legacy_dev
        )
        if dependencies is None:
            return
        dependency_groups["dev"] = dependencies
        del self.tool_poetry["dev-dependencies"]

    @staticmethod
    def _matching_group_name(groups: TomlTable, name: str) -> str | None:
        """Find a group using PEP 735's normalized name comparison."""
        normalized_name = re.sub(r"[-_.]+", "-", name).lower()
        for existing_name in groups:
            if re.sub(r"[-_.]+", "-", str(existing_name)).lower() == normalized_name:
                return str(existing_name)
        return None

    def _convert_group(
        self, group_name: str, group: TomlTable
    ) -> tuple[Array, set[str]] | None:
        from tomlkit import array, inline_table

        result = array()
        result.multiline(True)
        consumed_keys: set[str] = set()

        include_groups = group.get("include-groups")
        if include_groups is not None:
            if not isinstance(include_groups, Array) or not all(
                isinstance(name, str) for name in include_groups
            ):
                self.migrator.warnings.append(
                    f"[tool.poetry.group.{group_name}.include-groups] has an unsupported value; group kept."
                )
                return None
            include_replacements: list[Item] = []
            for included_group in include_groups:
                include = inline_table()
                include["include-group"] = included_group
                include_replacements.append(include)
            extend_array_preserving_comments(
                result, include_groups, include_replacements
            )
            consumed_keys.add("include-groups")

        dependencies = group.get("dependencies")
        if dependencies is not None:
            if not is_table(dependencies):
                self.migrator.warnings.append(
                    f"[tool.poetry.group.{group_name}.dependencies] is not a table; group kept."
                )
                return None
            converted_dependencies = self._convert_dependencies(
                f"tool.poetry.group.{group_name}.dependencies",
                dependencies,
                result,
            )
            if converted_dependencies is None:
                return None
            result = converted_dependencies
            consumed_keys.add("dependencies")

        if len(consumed_keys) == 0:
            return None
        return result, consumed_keys

    def _convert_dependencies(
        self,
        container_name: str,
        dependencies: TomlTable,
        target: Array | None = None,
    ) -> Array | None:
        from poetry.core.factory import Factory
        from poetry.core.packages.path_dependency import PathDependency
        from tomlkit import array

        result = target if target is not None else array()
        result.multiline(True)

        for dependency_name, raw_constraint in dependencies.items():
            constraints: list[object] = (
                list(raw_constraint)
                if isinstance(raw_constraint, Array)
                else [raw_constraint]
            )
            replacements: list[Item] = []
            for raw_item in constraints:
                constraint = deepcopy(raw_item)
                dependency = Factory.create_dependency(
                    dependency_name,
                    DependencyMigrator._dependency_spec(constraint),
                )
                if (
                    isinstance(dependency, PathDependency)
                    and not dependency.path.is_absolute()
                ):
                    self.migrator.warnings.append(
                        f"[{container_name}.{dependency_name}] uses a relative path and cannot be represented safely; group kept."
                    )
                    return None

                remaining_constraint = DependencyMigrator._without_pep508_fields(
                    constraint
                )
                if is_table(remaining_constraint) and len(remaining_constraint) > 0:
                    fields = ", ".join(
                        sorted(str(field) for field in remaining_constraint)
                    )
                    self.migrator.warnings.append(
                        f"[{container_name}.{dependency_name}] uses Poetry-only fields ({fields}); group kept."
                    )
                    return None

                try:
                    pep508 = render_pep508_requirement(
                        dependency,
                        keep_version_brackets=self.migrator._keep_pep508_version_brackets(),
                    )
                except UnrepresentableRequirementError:
                    self.migrator.warnings.append(
                        f"[{container_name}.{dependency_name}] cannot be represented safely in PEP 508; group kept."
                    )
                    return None
                converted = make_string(pep508, literal=self.migrator.literal)
                replacements.append(converted)

            if isinstance(raw_constraint, Array):
                extend_array_preserving_comments(result, raw_constraint, replacements)
            else:
                append_array_value(
                    result,
                    replacements[0],
                    require_item(raw_constraint, "dependency constraint"),
                )

        return result
