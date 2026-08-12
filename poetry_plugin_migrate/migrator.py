from __future__ import annotations

from collections.abc import Callable
from typing import ClassVar, Protocol

from poetry.core.constraints.version import VersionConstraint, parse_constraint
from tomlkit import TOMLDocument
from tomlkit.container import Container
from tomlkit.items import Array, Item, Table

from poetry_plugin_migrate.toml import (
    TomlTable,
    is_table,
    require_array,
    require_table,
)


class MigrationCommand(Protocol):
    """Console operations used by the migration engine."""

    def line(self, text: str) -> None: ...

    def confirm(self, question: str, default: bool = False) -> bool: ...

    def choice(
        self,
        question: str,
        choices: list[str],
        default: int,
        attempts: int | None = None,
        multiple: bool = False,
    ) -> object: ...


TableTransformer = Callable[[str, TomlTable], object]
ArrayTransformer = Callable[[int, list[object]], object]


_UNSET = object()


class SkipField(Exception):  # noqa: N818
    """Marker used in migration to skip field."""

    pass


class CopyModifiedField(Exception):  # noqa: N818
    """
    Marker used in migration to copy field to another container instead of moving it.

    Use `CopyModifiedField.args[0]` and `CopyModifiedField.args[1]` to get the new value for copy and update.
    """

    def __init__(self, target_value: object, update_value: object) -> None:
        super().__init__()
        self.target_value = target_value
        self.update_value = update_value


class RemoveField(Exception):  # noqa: N818
    """Marker used when a transformer consumed a source field without a target move."""


class UpdateField(Exception):  # noqa: N818
    """Marker used when a transformer only needs to update the source field."""

    def __init__(self, update_value: object) -> None:
        super().__init__()
        self.update_value = update_value


class Migrator:
    """
    Class to migrate pyproject.toml from Poetry v1 to v2 (PEP-621 compliant).

    Items marked with *prompt* will be handled with a prompt,
    and will be skipped if `skip` is set.

    What will be moved from `[tool.poetry]` to `[project]`:
    - Same-named fields
        - `name`, `description`, `license`, `keywords`, `urls`
        - `version` (*prompt*, if user do not need dynamic versioning)
        - `readme` (if only one readme is set)
        - `classifiers` (*prompt*, if user do not need classifier enrichment)
    - `homepage` => `[project.urls.homepage]`
    - `repository` => `[project.urls.repository]`
    - `documentation` => `[project.urls.documentation]`
    - `plugins` => `[project.entry-points]`
    - `scripts` (only for those are not of type `file`, e.g. `{ reference = "some_binary.exe", type = "file" }`)

    What needs value transformation after moving from `[tool.poetry]` to `[project]`:
    - `authors`, `maintainers`
        - From `"name <email>"` to `{"name": name, "email": email}`
    - Dependencies
        - `dependencies`
        - `extras` => `[project.optional-dependencies]`
            - If value is a dict with only `version` and `optional = true`
        - `dependencies.python` => `[project.requires-python]` (*prompt*, if user tends to put it here)

    What will be kept in `[tool.poetry]` and added in `[project.dynamic]`:
    - `version` (*prompt*, if user needs dynamic versioning)
    - `readme` (if multiple readmes are set)
    - `classifiers` (*prompt*, if user needs classifier enrichment)
    - `dependencies` (*prompt*, if user tends to completely keep it)
    - `dependencies` (only for those have Poetry-specific features, e.g. `source`, `allow-prereleases`, arrays)
    - `dependencies.python`, with `requires-python` added as `dynamic` (*prompt*, if user tends to keep it)

    Other changes:
    - Add or update `[tool.poetry.requires-poetry]` with a Poetry 2.2.1 constraint (*prompt*)
    - Update `[build-system.requires]` to `poetry-core>=2.0.0,<3.0.0` if `poetry-core` is set (*prompt*)
    """

    command: MigrationCommand
    """Command instance to run migration in context of."""

    skip: bool
    """Skip asking and use default values for prompts."""

    literal: bool
    """Whether to use literal strings for TOML values."""

    warnings: list[str]
    """List of warnings encountered during migration."""

    CONSTRAINT_PRESETS: ClassVar[list[str]] = [
        ">=2.0",
        ">=2.0,<3.0",
        ">=2.0.0",
        ">=2.0.0,<3.0.0",
    ]
    """List of constraints of Poetry v2 to be used in migration."""

    POETRY_CONSTRAINT_PRESETS: ClassVar[list[str]] = [
        ">=2.2.1",
        ">=2.2.1,<3.0.0",
    ]
    """Poetry constraints compatible with dependency-group migration."""

    def __init__(self, command: MigrationCommand, skip: bool, literal: bool) -> None:
        self.warnings = []
        self.skip = skip
        self.command = command
        self.literal = literal
        self._keep_version_brackets: bool | None = None

    def _keep_pep508_version_brackets(self) -> bool:
        """Return the cached output-style choice for generated requirements."""
        if self._keep_version_brackets is None:
            remove_brackets = self._prompt(
                "Remove brackets from PEP 508 version specifiers?",
                default=True,
                additional_info=(
                    "Per PEP 508, brackets around version specifiers "
                    "(e.g. <comment>package (>=1.0,<2.0)</comment>) "
                    "should not be generated, but Poetry includes them by default. "
                    "Choose whether to remove them in the migrated output."
                ),
            )
            self._keep_version_brackets = not remove_brackets
        return self._keep_version_brackets

    def _move(
        self,
        field: str,
        from_container: TomlTable,
        to_container: TomlTable | Array,
        *,
        from_container_key: str,
        to_container_key: str,
        update_value: object = _UNSET,
        target_value: object = _UNSET,
        remove_source: bool = True,
    ) -> bool:
        """
        Move field from one container to another container.

        If field is already in `to_container`, add a warning and not overwrite it.

        If `update_value` is set, copies the value to `to_container` instead of moving it,
        then updates the value in `from_container`.
        """
        try:
            field_value: object = from_container[field]
        except KeyError:
            return False

        value_to_move: object = field_value if target_value is _UNSET else target_value

        # Move the field value to the to_container.  A different existing target
        # is a real conflict: preserve the legacy source instead of silently
        # deleting information the user has not accepted losing.
        if not isinstance(to_container, Array):
            if field in to_container:
                if to_container[field] != value_to_move:
                    self.warnings.append(
                        f"[{to_container_key}.{field}] and "
                        f"[{from_container_key}.{field}] are both set to "
                        "different values. Both values were kept."
                    )
                    return False
                self.warnings.append(
                    f"[{to_container_key}.{field}] and [{from_container_key}.{field}] are both set. "
                    "The duplicate legacy value will be removed."
                )
            else:
                to_container[field] = value_to_move

        else:
            if value_to_move in to_container:
                self.warnings.append(
                    f"Value {value_to_move} is already in [{to_container_key}] "
                    f"and will be removed from [{from_container_key}]."
                )
            else:
                if isinstance(value_to_move, Item) and value_to_move.trivia.comment:
                    to_container.add_line(
                        value_to_move,
                        comment=value_to_move.trivia.comment.removeprefix("#").lstrip(),
                    )
                else:
                    to_container.append(value_to_move)

        # Remove / update field in from_container
        if remove_source:
            if update_value is not _UNSET:
                # Dependency transformers normally mutate a copied value and
                # return it here. Avoid assigning the exact same object because
                # tomlkit containers maintain additional internal indexes.
                if from_container[field] is not update_value:
                    from_container[field] = update_value
            else:
                del from_container[field]

        return True

    def _move_sub_container(
        self,
        sub_container_name: str,
        from_container: TomlTable,
        to_container: TomlTable | Array,
        *,
        from_container_key: str,
        to_container_key: str,
        table_transformer: TableTransformer | None = None,
        array_transformer: ArrayTransformer | None = None,
    ) -> None:
        """
        Move all items in a table/array in `from_container` to `to_container`.

        If field is already in `to_container`, add a warning and not overwrite it.
        """
        if sub_container_name not in from_container:
            return

        from_sub_container = from_container[sub_container_name]

        if is_table(from_sub_container):
            original_keys = tuple(from_sub_container.keys())
            moved_keys: list[str] = []
            updates: dict[str, object] = {}
            for from_key in original_keys:
                # Do not run a potentially mutating transformer when the target
                # already contains a different value for the same key.
                if is_table(to_container) and from_key in to_container:
                    self.warnings.append(
                        f"[{to_container_key}.{from_key}] and "
                        f"[{from_container_key}.{sub_container_name}.{from_key}] "
                        "are both set. The legacy value was kept for review."
                    )
                    continue

                update_value = _UNSET
                target_value = _UNSET

                if table_transformer:
                    try:
                        target_value = table_transformer(from_key, from_sub_container)
                    except SkipField:
                        continue
                    except RemoveField:
                        moved_keys.append(from_key)
                        continue
                    except UpdateField as e:
                        updates[from_key] = e.update_value
                        continue
                    except CopyModifiedField as e:
                        target_value = e.target_value
                        update_value = e.update_value

                moved = self._move(
                    from_key,
                    from_sub_container,
                    to_container,
                    from_container_key=f"{from_container_key}.{sub_container_name}",
                    to_container_key=to_container_key,
                    update_value=update_value,
                    target_value=target_value,
                    remove_source=False,
                )

                if not moved:
                    continue
                if update_value is _UNSET:
                    moved_keys.append(from_key)
                else:
                    updates[from_key] = update_value

            # Deleting an emptied nested tomlkit table item-by-item and then
            # deleting its parent can corrupt tomlkit's internal table map (the
            # root cause reported in Issue #1). Delete the parent directly when
            # every item moved; otherwise only remove the successfully moved
            # keys and retain skipped/conflicting values.
            remaining_keys = set(original_keys) - set(moved_keys)
            if not remaining_keys:
                del from_container[sub_container_name]
                return

            for from_key in moved_keys:
                del from_sub_container[from_key]
            for from_key, update_value in updates.items():
                if from_sub_container[from_key] is not update_value:
                    from_sub_container[from_key] = update_value

        elif isinstance(from_sub_container, Array):
            if not isinstance(to_container, Array):
                raise TypeError(
                    f"Cannot move list [{from_container_key}.{sub_container_name}] "
                    f"to non-list [{to_container_key}]"
                )

            # Collect items in forward order to preserve original ordering.
            # items_to_move and items_to_keep hold the (possibly transformed) values.
            items_to_move: list[object] = []
            items_to_keep: list[object] = []
            source_values: list[object] = list(from_sub_container)
            for i, source_value in enumerate(source_values):
                transformed_value = source_value
                if array_transformer:
                    try:
                        transformed_value = array_transformer(i, source_values)
                    except SkipField:
                        items_to_keep.append(source_value)
                        continue
                items_to_move.append(transformed_value)

            for item in items_to_move:
                if item not in to_container:
                    to_container.append(item)

            if len(items_to_keep) == 0:
                del from_container[sub_container_name]
                return

            # Clear source and re-add only kept items
            while len(from_sub_container) > 0:
                del from_sub_container[-1]
            for item in items_to_keep:
                from_sub_container.append(item)

        else:
            raise TypeError(f"Unexpected type {type(from_sub_container)}")

        if sub_container_name in from_container and len(from_sub_container) == 0:
            del from_container[sub_container_name]

    def _prompt(
        self, question: str, default: bool = False, additional_info: str | None = None
    ) -> bool:
        """Prompt user for a yes/no question."""

        if self.skip:
            return default
        if additional_info:
            self.command.line(additional_info)
        result = self.command.confirm(f"<question>{question}</question>", default)
        self.command.line("")
        return result

    def _choice(
        self,
        question: str,
        choices: list[str],
        default: int,
        attempts: int | None = None,
        additional_info: str | None = None,
    ) -> str:
        """Prompt user for a choice from a list of choices."""

        if self.skip:
            return choices[default]
        if additional_info:
            self.command.line(additional_info)
        result = self.command.choice(question, choices, default, attempts, False)
        self.command.line("")

        if isinstance(result, int):
            return choices[result]
        if isinstance(result, str):
            return result
        raise TypeError(f"Expected a single choice, got {type(result).__name__}")

    def _select_constraint(
        self,
        key: str,
        additional_info: str | None = None,
        presets: list[str] | None = None,
    ) -> VersionConstraint | None:
        """Prompt user for a constraint to update a field."""

        choices = [*(presets or self.CONSTRAINT_PRESETS), "No update"]
        result = self._choice(
            f"Update <b>[{key}]</b> to which constraint?",
            choices,
            default=len(choices) - 1,
            additional_info=additional_info,
        )
        return None if result == "No update" else parse_constraint(result)

    # ------------------------------------------------------------------
    # Orchestrator
    # ------------------------------------------------------------------

    def run(self, pyproject_document: TOMLDocument) -> TOMLDocument:
        """Run migration."""

        from copy import deepcopy

        new_document: TOMLDocument = deepcopy(pyproject_document)

        # tomlkit represents tables whose declarations are separated by other
        # top-level tables with an OutOfOrderTableProxy. Deleting keys through
        # that proxy can invalidate its table indexes after one backing table
        # becomes empty. Consolidate only [tool.poetry] before any mutation so
        # all later operations use an ordinary Table.
        self._consolidate_tool_poetry(new_document)

        tool_poetry = self._get_tool_poetry(new_document)
        if tool_poetry is None:
            return new_document

        project = self._ensure_project_table(new_document)

        # Phase 1: Direct field moves
        self._migrate_direct_fields(tool_poetry, project)
        self._migrate_urls(tool_poetry, project)
        self._migrate_plugins(tool_poetry, project)
        self._migrate_scripts(tool_poetry, project)

        # Phase 2: User-prompted fields
        self._migrate_version(tool_poetry, project)
        self._migrate_classifiers(tool_poetry, project)
        self._migrate_readme(tool_poetry, project)

        # Phase 3: Value transforms
        self._migrate_persons(tool_poetry, project)

        # Phase 4: Dependencies (delegated)
        if "dependencies" in tool_poetry:
            from poetry_plugin_migrate.dependencies import DependencyMigrator

            DependencyMigrator(self, tool_poetry, project).run()

        # Phase 4b: PEP 735 groups. Optional standard groups require Poetry >=2.2.1.
        if "group" in tool_poetry or "dev-dependencies" in tool_poetry:
            from poetry_plugin_migrate.dependencies import DependencyGroupMigrator

            DependencyGroupMigrator(self, new_document, tool_poetry).run()

        # Phase 5: Metadata updates
        self._migrate_requires_poetry(tool_poetry)
        self._migrate_build_system(new_document)

        # Clean up empty dependencies array
        project_dependencies = project.get("dependencies")
        if isinstance(project_dependencies, Array) and len(project_dependencies) == 0:
            del project["dependencies"]

        return new_document

    @staticmethod
    def _consolidate_tool_poetry(doc: TOMLDocument) -> None:
        """Replace a split ``[tool.poetry]`` proxy with one real table.

        TOML permits child tables such as ``[tool.poetry.dependencies]`` to be
        declared after unrelated tables. tomlkit exposes the resulting parent
        as an ``OutOfOrderTableProxy``. Its deletion bookkeeping is unsafe for
        the migration's repeated moves, so merge the proxy's backing tables
        before editing them. Existing tomlkit items are moved rather than
        recreated, preserving their values and attached trivia.
        """
        from tomlkit.container import OutOfOrderTableProxy

        tool = doc.get("tool")
        if not is_table(tool):
            return
        tool_poetry = tool.get("poetry")
        if not isinstance(tool_poetry, OutOfOrderTableProxy):
            return

        backing_tables = list(tool_poetry._tables)
        if len(backing_tables) < 2:
            return

        combined_body = [
            (key, item)
            for backing_table in backing_tables
            for key, item in backing_table.value.body
        ]
        target = backing_tables[-1]
        target.clear()
        for key, item in combined_body:
            target.append(key, item)

        def remove_table(container: Container, table_to_remove: Table) -> bool:
            for index, (_key, item) in enumerate(list(container.body)):
                if item is table_to_remove:
                    # A container can hold more than one out-of-order table
                    # with the same key. Removing by key would also remove the
                    # consolidated target, so remove this exact body item.
                    container._remove_at(index)
                    return True
                if isinstance(item, Table) and remove_table(
                    item.value, table_to_remove
                ):
                    return True
            return False

        for backing_table in backing_tables[:-1]:
            if not remove_table(doc, backing_table):
                raise RuntimeError("Could not consolidate split [tool.poetry] table")

    # ------------------------------------------------------------------
    # Infrastructure helpers
    # ------------------------------------------------------------------

    def _get_tool_poetry(self, doc: TOMLDocument) -> TomlTable | None:
        """Extract [tool.poetry] from document, returning None if absent."""
        tool = doc.get("tool")
        if not is_table(tool):
            self.warnings.append(
                "[tool.poetry] section not found. Related migration skipped."
            )
            return None
        tool_poetry = tool.get("poetry")
        if not is_table(tool_poetry):
            self.warnings.append(
                "[tool.poetry] section not found. Related migration skipped."
            )
            return None
        return tool_poetry

    def _ensure_project_table(self, doc: TOMLDocument) -> TomlTable:
        """Ensure [project] table exists and return it."""
        from tomlkit import table

        if "project" not in doc:
            doc["project"] = table()
        return require_table(doc["project"], "project")

    def _add_dynamic(self, project: TomlTable, field: str) -> None:
        """Add given field to [project.dynamic] and remove it from [project]."""
        from tomlkit import array

        if field in project:
            self.warnings.append(
                f"[project.{field}] already exists and will be removed during adding it to [project.dynamic]."
            )
            del project[field]
        if "dynamic" not in project:
            project["dynamic"] = array()
        dynamic = require_array(project["dynamic"], "project.dynamic")
        dynamic.multiline(True)
        if field not in dynamic:
            dynamic.append(field)

    # ------------------------------------------------------------------
    # Phase 1: Direct field moves
    # ------------------------------------------------------------------

    def _migrate_direct_fields(
        self, tool_poetry: TomlTable, project: TomlTable
    ) -> None:
        """Migrate same-named fields: name, description, license, keywords."""
        for field in ("name", "description", "license", "keywords"):
            self._move(
                field,
                tool_poetry,
                project,
                from_container_key="tool.poetry",
                to_container_key="project",
            )

    def _migrate_urls(self, tool_poetry: TomlTable, project: TomlTable) -> None:
        """Migrate homepage/repository/documentation and custom [tool.poetry.urls]."""
        from tomlkit import table

        url_fields = ("homepage", "repository", "documentation")
        if any(field in tool_poetry for field in url_fields) or "urls" in tool_poetry:
            if "urls" not in project:
                project["urls"] = table()
            urls = require_table(project["urls"], "project.urls")
            for field in url_fields:
                self._move(
                    field,
                    tool_poetry,
                    urls,
                    from_container_key="tool.poetry",
                    to_container_key="project.urls",
                )
            self._move_sub_container(
                "urls",
                tool_poetry,
                urls,
                from_container_key="tool.poetry",
                to_container_key="project.urls",
            )

    def _migrate_plugins(self, tool_poetry: TomlTable, project: TomlTable) -> None:
        """Migrate [tool.poetry.plugins] to [project.entry-points]."""
        from tomlkit import table

        if "plugins" in tool_poetry:
            if "entry-points" not in project:
                project["entry-points"] = table()
            entry_points = require_table(
                project["entry-points"], "project.entry-points"
            )
            self._move_sub_container(
                "plugins",
                tool_poetry,
                entry_points,
                from_container_key="tool.poetry",
                to_container_key="project.entry-points",
            )

    def _migrate_scripts(self, tool_poetry: TomlTable, project: TomlTable) -> None:
        """Migrate [tool.poetry.scripts] to [project.scripts], skipping file-type."""
        from tomlkit import table

        if "scripts" in tool_poetry:
            if "scripts" not in project:
                project["scripts"] = table()
            scripts = require_table(project["scripts"], "project.scripts")
            self._move_sub_container(
                "scripts",
                tool_poetry,
                scripts,
                from_container_key="tool.poetry",
                to_container_key="project.scripts",
                table_transformer=self._transform_script_item,
            )

    @staticmethod
    def _transform_script_item(script_name: str, tool_poetry_scripts: TomlTable) -> str:
        script = tool_poetry_scripts[script_name]
        if not isinstance(script, str):
            raise SkipField()
        return script

    # ------------------------------------------------------------------
    # Phase 2: User-prompted fields
    # ------------------------------------------------------------------

    def _migrate_version(self, tool_poetry: TomlTable, project: TomlTable) -> None:
        """Migrate version: prompt for dynamic vs static."""
        if "version" not in tool_poetry:
            return

        if self._prompt(
            "Keeps Poetry managing version in <b>[tool.poetry]</b> with dynamic versioning?",
            default=False,
            additional_info=(
                "<b>[tool.poetry.version]</b> found. "
                "If you want to set the version dynamically via "
                "<info>poetry build --local-version</info> or you are using a plugin, which "
                "sets the version dynamically, you should use dynamic versioning that "
                "keeps 'version' in <b>[tool.poetry]</b> and "
                "adds 'version' to <b>[project.dynamic]</b>. "
                "Otherwise, 'version' will be moved to <b>[project]</b>."
            ),
        ):
            self._add_dynamic(project, "version")
        else:
            self._move(
                "version",
                tool_poetry,
                project,
                from_container_key="tool.poetry",
                to_container_key="project",
            )

    def _migrate_classifiers(self, tool_poetry: TomlTable, project: TomlTable) -> None:
        """Migrate classifiers: prompt for auto-enrichment vs manual."""
        from tomlkit import array

        if "classifiers" not in tool_poetry:
            return

        if self._prompt(
            "Keep Poetry managing classifiers in <b>[tool.poetry]</b> with auto-enrichment?",
            default=True,
            additional_info=(
                "Per default Poetry determines classifiers for supported "
                "Python versions and license automatically. If you define classifiers "
                "in <b>[project]</b>, you disable the automatic enrichment. In other words, "
                "you have to define all classifiers manually. "
                "If you want to use Poetry's automatic enrichment of classifiers, "
                "they should be kept in <b>[tool.poetry]</b> and 'classifiers' "
                "should be added to <b>[project.dynamic]</b>. "
            ),
        ):
            self._add_dynamic(project, "classifiers")
        else:
            if "classifiers" not in project:
                project["classifiers"] = array()
            classifiers = require_array(project["classifiers"], "project.classifiers")
            classifiers.multiline(True)
            self._move_sub_container(
                "classifiers",
                tool_poetry,
                classifiers,
                from_container_key="tool.poetry.classifiers",
                to_container_key="project.classifiers",
            )

    def _migrate_readme(self, tool_poetry: TomlTable, project: TomlTable) -> None:
        """Migrate readme: single file moves to [project], multiple stay dynamic."""
        if "readme" not in tool_poetry:
            return

        readme = tool_poetry["readme"]
        if isinstance(readme, str):
            self._move(
                "readme",
                tool_poetry,
                project,
                from_container_key="tool.poetry",
                to_container_key="project",
            )
        elif isinstance(readme, Array):
            self._add_dynamic(project, "readme")
        else:
            self.warnings.append(
                f"Unexpected type of [tool.poetry.readme]: {type(readme)}"
            )

    # ------------------------------------------------------------------
    # Phase 3: Value transforms
    # ------------------------------------------------------------------

    def _migrate_persons(self, tool_poetry: TomlTable, project: TomlTable) -> None:
        """Migrate authors and maintainers: "name <email>" -> {name, email}."""
        from tomlkit import array

        for arr_name in ("authors", "maintainers"):
            if arr_name in tool_poetry:
                if arr_name not in project:
                    project[arr_name] = array()
                people = require_array(project[arr_name], f"project.{arr_name}")
                people.multiline(True)
                self._move_sub_container(
                    arr_name,
                    tool_poetry,
                    people,
                    from_container_key="tool.poetry",
                    to_container_key=f"project.{arr_name}",
                    array_transformer=self._transform_person_item,
                )

    @staticmethod
    def _transform_person_item(
        person_index: int, tool_poetry_person: list[object]
    ) -> object:
        from tomlkit import inline_table

        person = tool_poetry_person[person_index]
        assert isinstance(person, str)

        name, _, email = person.partition(" <")
        email = email.rstrip(">")

        result = inline_table()
        result["name"] = name
        if email:
            result["email"] = email

        return result

    # ------------------------------------------------------------------
    # Phase 5: Metadata updates
    # ------------------------------------------------------------------

    def _migrate_requires_poetry(self, tool_poetry: TomlTable) -> None:
        """Add or update [tool.poetry.requires-poetry]."""
        from tomlkit import string

        if "requires-poetry" not in tool_poetry:
            target_constraint = self._select_constraint(
                "tool.poetry.requires-poetry", presets=self.POETRY_CONSTRAINT_PRESETS
            )
            if target_constraint:
                tool_poetry["requires-poetry"] = string(
                    str(target_constraint), literal=self.literal
                )
        else:
            constraint = parse_constraint(tool_poetry["requires-poetry"])
            target_constraint = self._select_constraint(
                "tool.poetry.requires-poetry",
                additional_info=(
                    "<b>[tool.poetry.requires-poetry]</b> found with value "
                    f"<comment>{constraint}</comment>."
                ),
                presets=self.POETRY_CONSTRAINT_PRESETS,
            )
            if target_constraint:
                if not constraint.intersect(target_constraint).is_empty():
                    tool_poetry["requires-poetry"] = string(
                        str(target_constraint), literal=self.literal
                    )
                else:
                    self.warnings.append(
                        "Not updating [tool.poetry.requires-poetry] "
                        f"since current value {constraint} is not compatible with {target_constraint}."
                    )

    def _migrate_build_system(self, doc: TOMLDocument) -> None:
        """Update [build-system.requires] poetry-core version."""
        from poetry.core.packages.dependency import Dependency
        from tomlkit import string

        if "build-system" not in doc:
            return
        build_system = require_table(doc["build-system"], "build-system")
        if "requires" not in build_system:
            return

        requires = require_array(build_system["requires"], "build-system.requires")
        for i, requirement in enumerate(requires):
            if not isinstance(requirement, str):
                raise TypeError("[build-system.requires] entries must be strings")
            dependency = Dependency.create_from_pep_508(requirement)
            if dependency.name == "poetry-core":
                constraint = dependency.constraint
                if constraint.is_any():
                    target_constraint = self._select_constraint(
                        "build-system.requires.poetry-core"
                    )
                    if target_constraint:
                        dependency.constraint = target_constraint
                        from poetry_plugin_migrate.requirements import (
                            UnrepresentableRequirementError,
                            render_pep508_requirement,
                        )

                        try:
                            rendered = render_pep508_requirement(
                                dependency,
                                keep_version_brackets=self._keep_pep508_version_brackets(),
                            )
                        except UnrepresentableRequirementError:
                            self.warnings.append(
                                "Not updating [build-system.requires] poetry-core because the generated requirement did not round-trip safely."
                            )
                        else:
                            requires[i] = string(rendered, literal=self.literal)
                    break
