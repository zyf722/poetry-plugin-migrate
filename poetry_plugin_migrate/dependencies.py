from __future__ import annotations

import re
from collections.abc import Mapping
from copy import deepcopy
from typing import TYPE_CHECKING, TypeAlias

from tomlkit import TOMLDocument
from tomlkit.items import Array, InlineTable, String

from poetry_plugin_migrate.migrator import (
    CopyModifiedField,
    RemoveField,
    SkipField,
    UpdateField,
)
from poetry_plugin_migrate.requirements import (
    UnrepresentableRequirementError,
    render_pep508_requirement,
)
from poetry_plugin_migrate.toml import (
    TomlTable,
    is_table,
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

    MULTI_CONSTRAINT_PREFIX = "pypoetrymigrate$"

    def __init__(
        self, migrator: Migrator, tool_poetry: TomlTable, project: TomlTable
    ) -> None:
        self.migrator = migrator
        self.tool_poetry = tool_poetry
        self.project = project
        self.deps = require_table(
            tool_poetry["dependencies"], "tool.poetry.dependencies"
        )

    def run(self) -> None:
        self.keep_version_brackets = self.migrator._keep_pep508_version_brackets()
        self._migrate_requires_python()
        unsafe_dependencies = self._unsafe_main_dependencies()
        if unsafe_dependencies:
            self._keep_unsafe_dependencies(unsafe_dependencies)
            return

        self._expand_multi_constraints()
        self._migrate_optional_dependencies()
        self._migrate_main_dependencies()
        self._rebuild_multi_constraints()

    def _unsafe_main_dependencies(self) -> dict[str, set[str]]:
        """Return dependencies that cannot be represented safely in PEP 508."""
        from poetry.core.factory import Factory
        from poetry.core.packages.path_dependency import PathDependency

        unsafe: dict[str, set[str]] = {}
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
        return unsafe

    def _keep_unsafe_dependencies(
        self, unsafe_dependencies: dict[str, set[str]]
    ) -> None:
        """Keep the complete Poetry dependency model when migration is lossy."""
        dependency_list = "; ".join(
            f"{name} ({', '.join(sorted(reasons))})"
            for name, reasons in sorted(unsafe_dependencies.items())
        )
        if "dependencies" in self.project:
            raise ValueError(
                "Cannot safely migrate Poetry dependencies because dependencies "
                f"with Poetry-only semantics ({dependency_list}) coexist with "
                "[project.dependencies]. Remove the conflict or migrate these "
                "dependencies manually."
            )

        self.migrator.warnings.append(
            f"Dependencies {dependency_list} use semantics that cannot be represented "
            "completely in PEP 508 project metadata. All dependencies and extras "
            "were kept in [tool.poetry] to preserve dependency semantics."
        )
        self.migrator._add_dynamic(self.project, "dependencies")

    # ------------------------------------------------------------------
    # Step 1: Expand multi-constraint dependencies
    # ------------------------------------------------------------------

    def _expand_multi_constraints(self) -> None:
        """Explode list constraints like [a, b] into temp keys."""
        for package_name in tuple(self.deps.keys()):
            constraints = self.deps[package_name]
            if isinstance(constraints, Array):
                for i, constraint in enumerate(constraints):
                    temp_name = f"{self.MULTI_CONSTRAINT_PREFIX}{package_name}${i}"
                    self.deps[temp_name] = constraint
                del self.deps[package_name]

    # ------------------------------------------------------------------
    # Step 2: requires-python
    # ------------------------------------------------------------------

    def _migrate_requires_python(self) -> None:
        """Handle migration of the python version constraint."""
        from poetry.core.constraints.version import parse_constraint
        from tomlkit import string

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
            self.project["requires-python"] = string(
                str(python_constraint), literal=self.migrator.literal
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
        from tomlkit import table

        if "extras" not in self.tool_poetry:
            return

        if "optional-dependencies" not in self.project:
            self.project["optional-dependencies"] = table()
        optional_dependencies = require_table(
            self.project["optional-dependencies"], "project.optional-dependencies"
        )

        self.migrator._move_sub_container(
            "extras",
            self.tool_poetry,
            optional_dependencies,
            from_container_key="tool.poetry",
            to_container_key="project.optional-dependencies",
            table_transformer=self._transform_optional_dependency_item,
        )

    def _transform_optional_dependency_item(
        self, extra_cluster_name: str, tool_poetry_extras: TomlTable
    ) -> Array:
        from poetry.core.factory import Factory
        from tomlkit import array

        # Build the target from a copy. Sharing a mutable tomlkit Array between
        # source and target tables can corrupt the container's internal indexes.
        extra_cluster = deepcopy(
            require_array(
                tool_poetry_extras[extra_cluster_name],
                f"tool.poetry.extras.{extra_cluster_name}",
            )
        )
        for i in range(len(extra_cluster) - 1, -1, -1):
            package_name = extra_cluster[i]
            if not isinstance(package_name, str):
                raise TypeError(
                    f"[tool.poetry.extras.{extra_cluster_name}] entries must be strings"
                )
            if package_name in self.deps:
                constraint: object = self.deps[package_name]
                dependency = Factory.create_dependency(
                    package_name, self._dependency_spec(constraint)
                )
                extra_cluster[i] = self._pep508_string(dependency, constraint)
                self._preserve_comment_on_array(extra_cluster, constraint)

                remaining_constraint = self._without_pep508_fields(constraint)
                if isinstance(constraint, str) or (
                    is_table(remaining_constraint) and len(remaining_constraint) == 0
                ):
                    del self.deps[package_name]
                else:
                    self.deps[package_name] = remaining_constraint
            else:
                extras_to_insert = array()
                keys_to_delete = []
                for dep_name in list(self.deps.keys()):
                    if dep_name.startswith(
                        f"{self.MULTI_CONSTRAINT_PREFIX}{package_name}"
                    ):
                        constraint = self.deps[dep_name]
                        extras_to_insert.append(
                            self._pep508_string(
                                Factory.create_dependency(
                                    package_name, self._dependency_spec(constraint)
                                ),
                                constraint,
                            )
                        )
                        self._preserve_comment_on_array(extra_cluster, constraint)

                        remaining_constraint = self._without_pep508_fields(
                            constraint, include_markers=False
                        )
                        if isinstance(constraint, str) or (
                            is_table(remaining_constraint)
                            and len(remaining_constraint) == 0
                        ):
                            keys_to_delete.append(dep_name)
                        else:
                            self.deps[dep_name] = remaining_constraint

                for dep_name in keys_to_delete:
                    del self.deps[dep_name]

                if len(extras_to_insert) > 0:
                    extra_cluster.pop(i)
                    for extra in extras_to_insert:
                        extra_cluster.insert(i, extra)

        if hasattr(extra_cluster, "multiline"):
            extra_cluster.multiline(True)

        return extra_cluster

    # ------------------------------------------------------------------
    # Step 4: Main dependencies
    # ------------------------------------------------------------------

    def _migrate_main_dependencies(self) -> None:
        """Migrate main dependencies to [project.dependencies] or keep dynamic."""
        if self.migrator._prompt(
            "Keeps dependencies in <b>[tool.poetry]</b>?",
            additional_info=(
                "<b>[tool.poetry.dependencies]</b> found. "
                "`dependencies` will be added to <b>[project.dynamic]</b> "
                "if you want to keep it in <b>[tool.poetry]</b>. "
            ),
        ):
            self.migrator._add_dynamic(self.project, "dependencies")
            return

        from tomlkit import array

        if "dependencies" not in self.project:
            self.project["dependencies"] = array()
        project_deps = require_array(
            self.project["dependencies"], "project.dependencies"
        )
        project_deps.multiline(True)

        from poetry.core.packages.dependency import Dependency

        project_deps_objs: list[Dependency] = []
        for requirement in project_deps:
            if not isinstance(requirement, str):
                raise TypeError("[project.dependencies] entries must be strings")
            project_deps_objs.append(Dependency.create_from_pep_508(requirement))

        self.migrator._move_sub_container(
            "dependencies",
            self.tool_poetry,
            project_deps,
            from_container_key="tool.poetry",
            to_container_key="project.dependencies",
            table_transformer=lambda orig_name, deps: self._transform_dependency_item(
                orig_name, deps, project_deps_objs
            ),
        )

    def _transform_dependency_item(
        self,
        orig_name: str,
        tool_poetry_deps: TomlTable,
        project_deps_objs: list[Dependency],
    ) -> object:
        from poetry.core.factory import Factory
        from poetry.core.packages.path_dependency import PathDependency

        original_constraint: object = tool_poetry_deps[orig_name]
        constraint = deepcopy(original_constraint)

        if orig_name.startswith(self.MULTI_CONSTRAINT_PREFIX):
            name = orig_name.split("$")[1]
        else:
            name = orig_name

        dependency = Factory.create_dependency(name, self._dependency_spec(constraint))
        if dependency.name == "python" or (
            isinstance(dependency, PathDependency) and not dependency.path.is_absolute()
        ):
            raise SkipField()

        if any(pd.name == dependency.name for pd in project_deps_objs):
            self.migrator.warnings.append(
                f"Dependency {dependency} is already defined in "
                "<b>[project.dependencies]</b> and it will be skipped."
            )
            raise SkipField()

        remaining_constraint = self._without_pep508_fields(
            constraint,
            ["optional"],
            include_markers=not orig_name.startswith(self.MULTI_CONSTRAINT_PREFIX),
        )

        if dependency.is_optional():
            if not is_table(remaining_constraint) or len(remaining_constraint) == 0:
                raise RemoveField()
            raise UpdateField(remaining_constraint)

        if isinstance(constraint, str) or (
            is_table(remaining_constraint) and len(remaining_constraint) == 0
        ):
            return self._pep508_string(dependency, original_constraint)
        raise CopyModifiedField(
            self._pep508_string(dependency, original_constraint),
            remaining_constraint,
        )

    # ------------------------------------------------------------------
    # Step 5: Rebuild multi-constraint dependencies
    # ------------------------------------------------------------------

    def _rebuild_multi_constraints(self) -> None:
        """Collapse temp keys back into arrays."""
        from tomlkit import array

        for package_name in tuple(self.deps.keys()):
            if package_name.startswith(self.MULTI_CONSTRAINT_PREFIX):
                constraint = self.deps[package_name]
                original = package_name.split("$")[1]
                if original not in self.deps:
                    self.deps[original] = array()
                rebuilt = require_array(
                    self.deps[original], f"tool.poetry.dependencies.{original}"
                )
                rebuilt.append(constraint)
                del self.deps[package_name]

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
        from tomlkit import string

        result = string(
            render_pep508_requirement(
                dependency,
                keep_version_brackets=self.keep_version_brackets,
            ),
            literal=self.migrator.literal,
        )
        source_item = require_item(source, "dependency constraint")
        result.trivia.indent = deepcopy(source_item.trivia.indent)
        result.trivia.comment_ws = deepcopy(source_item.trivia.comment_ws)
        result.trivia.comment = deepcopy(source_item.trivia.comment)
        result.trivia.trail = deepcopy(source_item.trivia.trail)
        return result

    @staticmethod
    def _preserve_comment_on_array(target: Array, source: object) -> None:
        """Keep a dependency-definition comment when rebuilding an extras array."""
        source_item = require_item(source, "dependency constraint")
        comment = source_item.trivia.comment
        if not comment:
            return
        text = comment.removeprefix("#").strip()
        existing = target.trivia.comment
        if existing:
            text = f"{existing.removeprefix('#').strip()}; {text}"
        target.comment(text)


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
            for included_group in include_groups:
                include = inline_table()
                include["include-group"] = included_group
                result.append(include)
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
        from tomlkit import array, string

        result = target if target is not None else array()
        result.multiline(True)

        for dependency_name, raw_constraint in dependencies.items():
            constraints: list[object] = (
                list(raw_constraint)
                if isinstance(raw_constraint, Array)
                else [raw_constraint]
            )
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
                converted = string(pep508, literal=self.migrator.literal)
                source_item = require_item(raw_item, "dependency constraint")
                comment = source_item.trivia.comment
                if comment:
                    result.add_line(
                        converted, comment=comment.removeprefix("#").lstrip()
                    )
                else:
                    result.append(converted)

        return result
