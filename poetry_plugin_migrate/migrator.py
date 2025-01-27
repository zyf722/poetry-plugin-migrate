from __future__ import annotations

from typing import TYPE_CHECKING

from poetry.core.constraints.version import parse_constraint

if TYPE_CHECKING:
    from typing import Any, Callable, ClassVar

    from poetry.console.commands.command import Command
    from tomlkit import TOMLDocument

    ItemTransformer = (
        Callable[[str, dict[str, Any]], Any] | Callable[[int, list[str]], Any]
    )


class SkipField(Exception):
    """Marker used in migration to skip field."""

    pass


class CopyModifiedField(Exception):
    """
    Marker used in migration to copy field to another container instead of moving it.

    Use `CopyModifiedField.args[0]` and `CopyModifiedField.args[1]` to get the new value for copy and update.
    """

    pass


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
    - Add `[tool.poetry.requires-poetry]` with value `>=2.0`
    - Update `[build-system.requires]` to `poetry-core>=2.0.0,<3.0.0` if `poetry-core` is set (*prompt*)
    """

    command: Command
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

    def __init__(self, command: Command, skip: bool, literal: bool):
        self.warnings = []
        self.skip = skip
        self.command = command
        self.literal = literal

    def _move(
        self,
        field_or_index: str | int,
        from_container: dict[str, Any] | list[Any],
        to_container: dict[str, Any] | list[Any],
        *,
        from_container_key: str,
        to_container_key: str,
        update_value: Any | None = None,
    ):
        """
        Move field from one container to another container.

        If field is already in `to_container`, add a warning and not overwrite it.

        If `update_value` is set, copies the value to `to_container` instead of moving it,
        then updates the value in `from_container`.
        """
        # Ensure the from_container is valid for the type of field_or_index
        if isinstance(from_container, dict) and isinstance(field_or_index, str):
            try:
                field_value = from_container[field_or_index]
            except KeyError:
                return

        elif isinstance(from_container, list) and isinstance(field_or_index, int):
            try:
                field_value = from_container[field_or_index]
            except IndexError:
                return
        else:
            raise ValueError("Invalid combination of field_or_index and from_container")

        # Move the field value to the to_container
        if isinstance(to_container, dict):
            assert isinstance(field_or_index, str), (
                "Expected field_or_index to be a string"
            )
            if field_or_index in to_container:
                pretty_field = str(
                    field_or_index
                )  # Assuming `key(field_or_index).as_string()` is to format the key
                self.warnings.append(
                    f"[{to_container_key}.{pretty_field}] and [{from_container_key}.{pretty_field}] are both set. "
                    "The former will be kept and the latter will be removed."
                )
            else:
                to_container[field_or_index] = field_value

        elif isinstance(to_container, list):
            if field_value in to_container:
                self.warnings.append(
                    f"Value {field_value} is already in [{to_container_key}] and will be remove from [{from_container_key}]."
                )
            else:
                to_container.append(field_value)

        # Remove / update field in from_container
        if update_value is not None:
            from_container[field_or_index] = update_value  # type: ignore[index]
        else:
            del from_container[field_or_index]  # type: ignore[arg-type]

    def _move_sub_container(
        self,
        sub_container_name: str,
        from_container: dict[str, Any],
        to_container: dict[str, Any] | list[Any],
        *,
        from_container_key: str,
        to_container_key: str,
        from_item_transformer: ItemTransformer | None = None,
    ):
        """
        Move all items in a table/array in `from_container` to `to_container`.

        If field is already in `to_container`, add a warning and not overwrite it.
        """
        if sub_container_name in from_container:
            from_sub_container = from_container[sub_container_name]

            if isinstance(from_sub_container, dict):
                for from_key in tuple(from_sub_container.keys()):
                    update_value = None

                    if from_item_transformer:
                        try:
                            from_sub_container[from_key] = from_item_transformer(
                                from_key,  # type: ignore[arg-type]
                                from_sub_container,  # type: ignore[arg-type]
                            )
                        except SkipField:
                            continue
                        except CopyModifiedField as e:
                            from_sub_container[from_key] = e.args[0]
                            update_value = e.args[1]

                    self._move(
                        from_key,
                        from_sub_container,
                        to_container,
                        from_container_key=f"{from_container_key}.{sub_container_name}",
                        to_container_key=to_container_key,
                        update_value=update_value,
                    )

            elif isinstance(from_sub_container, list):
                for i in range(len(from_sub_container) - 1, -1, -1):
                    if from_item_transformer:
                        try:
                            from_sub_container[i] = from_item_transformer(
                                i,  # type: ignore[arg-type]
                                from_sub_container,  # type: ignore[arg-type]
                            )
                        except SkipField:
                            continue

                    self._move(
                        i,
                        from_sub_container,
                        to_container,
                        from_container_key=f"{from_container_key}.{sub_container_name}",
                        to_container_key=to_container_key,
                    )

            else:
                raise TypeError(f"Unexpected type {type(from_sub_container)}")

            if len(from_sub_container) == 0:
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
        multiple: bool = False,
        additional_info: str | None = None,
    ):
        """Prompt user for a choice from a list of choices."""

        if self.skip:
            return choices[default]
        if additional_info:
            self.command.line(additional_info)
        result = self.command.choice(question, choices, default, attempts, multiple)
        self.command.line("")

        if isinstance(result, int):
            # If result is an index, convert it to the corresponding value
            return choices[result]

        return result

    def _select_constraint(self, key: str, additional_info: str | None = None):
        """Prompt user for a constraint to update a field."""

        choices = [*self.CONSTRAINT_PRESETS, "No update"]
        result = self._choice(
            f"Update <b>[{key}]</b> to which constraint?",
            choices,
            default=len(choices) - 1,
            additional_info=additional_info,
        )
        return None if result == "No update" else parse_constraint(result)

    def run(self, pyproject_document: TOMLDocument) -> TOMLDocument:
        """Run migration."""

        from copy import deepcopy

        from poetry.core.packages.dependency import Dependency
        from poetry.core.packages.path_dependency import PathDependency
        from tomlkit import array, inline_table, string, table

        new_document: dict[str, Any] = deepcopy(pyproject_document)

        if (
            "tool" not in new_document or "poetry" not in new_document["tool"]  # type: ignore[operator]
        ):
            self.warnings.append(
                "[tool.poetry] section not found. Related migration skipped."
            )
        else:
            # Migrate [tool.poetry]

            if "project" not in new_document:
                new_document["project"] = table()

            project = new_document["project"]
            tool_poetry = new_document["tool"]["poetry"]

            def add_dynamic(field: str):
                """Add given field to [project.dynamic] and remove it from [project]."""
                if field in project:
                    self.warnings.append(
                        f"[project.{field}] already exists and will be removed during adding it to [project.dynamic]."
                    )
                    del project[field]
                if "dynamic" not in project:
                    project["dynamic"] = array()
                if field not in project["dynamic"]:
                    project["dynamic"].append(field)

            # Directly-moved fields
            ## Same-named fields
            for field in (
                "name",
                "description",
                "license",
                "keywords",
            ):
                self._move(
                    field,
                    tool_poetry,
                    project,
                    from_container_key="tool.poetry",
                    to_container_key="project",
                )

            ## URLs
            url_fields = ("homepage", "repository", "documentation")
            if any(field in tool_poetry for field in url_fields):
                if "urls" not in project:
                    project["urls"] = table()
                urls = project["urls"]
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

            ## Plugins
            if "plugins" in tool_poetry:
                if "entry-points" not in project:
                    project["entry-points"] = table()
                entry_points = project["entry-points"]
                self._move_sub_container(
                    "plugins",
                    tool_poetry,
                    entry_points,
                    from_container_key="tool.poetry",
                    to_container_key="project.entry-points",
                )

            ## Scripts
            if "scripts" in tool_poetry:
                if "scripts" not in project:
                    project["scripts"] = table()
                scripts = project["scripts"]

                def transform_script_item(
                    script_name: str, tool_poetry_scripts: dict[str, Any]
                ):
                    script = tool_poetry_scripts[script_name]
                    if not isinstance(script, str):
                        # Keep scripts of type file in tool.poetry
                        raise SkipField()
                    return script

                self._move_sub_container(
                    "scripts",
                    tool_poetry,
                    scripts,
                    from_container_key="tool.poetry",
                    to_container_key="project.scripts",
                    from_item_transformer=transform_script_item,
                )

            # Fields needing prompt
            ## version
            if "version" in tool_poetry:
                if self._prompt(
                    "Keeps Poetry managing version in <b>[tool.poetry]</b> with dynamic versioning?",
                    default=True,
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
                    add_dynamic("version")
                else:
                    self._move(
                        "version",
                        tool_poetry,
                        project,
                        from_container_key="tool.poetry",
                        to_container_key="project",
                    )

            ## classifiers
            if "classifiers" in tool_poetry:
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
                    add_dynamic("classifiers")
                else:
                    # Move classifiers to [project] and remove from [tool.poetry]
                    self._move_sub_container(
                        "classifiers",
                        tool_poetry,
                        project["classifiers"],
                        from_container_key="tool.poetry.classifiers",
                        to_container_key="project.classifiers",
                    )

            ## readme
            if "readme" in tool_poetry:
                readme = tool_poetry["readme"]
                if isinstance(readme, str):
                    # Only one readme
                    self._move(
                        "readme",
                        tool_poetry,
                        project,
                        from_container_key="tool.poetry",
                        to_container_key="project",
                    )
                elif isinstance(readme, list):
                    # Multiple readmes
                    add_dynamic("readme")
                else:
                    self.warnings.append(
                        f"Unexpected type of [tool.poetry.readme]: {type(readme)}"
                    )

            # Value-transformed fields
            ## Authors, maintainers
            def transform_person_item(person_index: int, tool_poetry_person: list[str]):
                person = tool_poetry_person[person_index]
                assert isinstance(person, str)

                name, _, email = person.partition(" <")
                email = email.rstrip(">")

                result = inline_table()
                result["name"] = name
                if email:
                    result["email"] = email

                return result

            for arr_name in ("authors", "maintainers"):
                if arr_name in tool_poetry:
                    if arr_name not in project:
                        project[arr_name] = array()
                    self._move_sub_container(
                        arr_name,
                        tool_poetry,
                        project[arr_name],
                        from_container_key="tool.poetry",
                        to_container_key=f"project.{arr_name}",
                        from_item_transformer=transform_person_item,
                    )

            ## Dependencies
            if "dependencies" in tool_poetry:
                tool_poetry_dependencies: dict[str, Any] = tool_poetry["dependencies"]

                from poetry.core.factory import Factory

                # Expand multiple constraints
                MULTIPLE_CONSTRAINT_TEMP_NAME_PREFIX = "pypoetrymigrate$"
                for package_name in tuple(tool_poetry_dependencies.keys()):
                    constraints = tool_poetry_dependencies[package_name]
                    if isinstance(constraints, list):
                        for i, constraint in enumerate(constraints):
                            temp_name = f"{MULTIPLE_CONSTRAINT_TEMP_NAME_PREFIX}{package_name}${i}"
                            tool_poetry_dependencies[temp_name] = constraint
                        del tool_poetry_dependencies[package_name]

                def remove_fields_from_constraint(
                    constraint: dict[str, Any],
                    fields: list[str] = [],
                    include_markers: bool = True,
                ):
                    if isinstance(constraint, dict):
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
                            fields.extend(
                                (
                                    "python",
                                    "platform",
                                    "markers",
                                    "extras",  # This is extras for dependency itself, not the project
                                )
                            )

                        for field in fields:
                            if field in constraint:
                                del constraint[field]

                ### requires-python
                if (
                    "python" in tool_poetry_dependencies
                    and "requires-python" not in project
                ):
                    # Python constraint only defined in [tool.poetry.dependencies]

                    choices = [
                        "Move to <b>[project.requires-python]</b>",
                        "Add `requires-python` to <b>[project.dynamic]</b>",
                        "Copy value to <b>[project.requires-python]</b>",
                        "No migration and keep it as-is",
                    ]
                    migrate_python = self._choice(
                        "How to migrate <b>[tool.poetry.dependencies.python]</b>?",
                        choices,
                        default=2,
                    )
                    if migrate_python in (choices[0], choices[2]):
                        python_constraint = parse_constraint(
                            tool_poetry_dependencies["python"]
                        )
                        project["requires-python"] = string(
                            str(python_constraint), literal=self.literal
                        )

                        if migrate_python == choices[0]:
                            # Remove python from [tool.poetry.dependencies]
                            del tool_poetry_dependencies["python"]

                    elif migrate_python == choices[1]:
                        add_dynamic("requires-python")

                ### Optional dependencies
                if "extras" in tool_poetry:
                    if "optional-dependencies" not in project:
                        project["optional-dependencies"] = table()
                    optional_dependencies = project["optional-dependencies"]

                    def transform_optional_dependency_item(
                        extra_cluster_name: str, tool_poetry_extras: dict[str, Any]
                    ):
                        extra_cluster: list[str] = tool_poetry_extras[
                            extra_cluster_name
                        ]
                        for i in range(len(extra_cluster) - 1, -1, -1):
                            package_name = extra_cluster[i]
                            if package_name in tool_poetry_dependencies:
                                constraint = tool_poetry_dependencies[package_name]
                                dependency = Factory.create_dependency(
                                    package_name, constraint
                                )
                                extra_cluster[i] = string(
                                    dependency.to_pep_508(), literal=self.literal
                                )

                                # Clean up constraint
                                # we leave "optional" here for later migration
                                remove_fields_from_constraint(constraint)
                                if len(constraint) == 0 or isinstance(constraint, str):
                                    del tool_poetry_dependencies[package_name]
                            else:
                                # Consider expanded dependencies
                                extras_to_insert = array()
                                for dep, constraint in tool_poetry_dependencies.items():
                                    if dep.startswith(
                                        f"{MULTIPLE_CONSTRAINT_TEMP_NAME_PREFIX}{package_name}"
                                    ):
                                        extras_to_insert.append(
                                            string(
                                                Factory.create_dependency(
                                                    package_name, constraint
                                                ).to_pep_508(),
                                                literal=self.literal,
                                            )
                                        )

                                        # Clean up constraint
                                        # we leave "optional" here for later migration
                                        remove_fields_from_constraint(
                                            constraint,
                                            include_markers=False,  # keep markers for expanded dependencies
                                        )
                                        if len(constraint) == 0 or isinstance(
                                            constraint, str
                                        ):
                                            del tool_poetry_dependencies[dep]

                                if len(extras_to_insert) > 0:
                                    extra_cluster.pop(i)
                                    for extra in extras_to_insert:
                                        extra_cluster.insert(i, extra)

                        return extra_cluster

                    self._move_sub_container(
                        "extras",
                        tool_poetry,
                        optional_dependencies,
                        from_container_key="tool.poetry",
                        to_container_key="project.optional-dependencies",
                        from_item_transformer=transform_optional_dependency_item,
                    )

                ### Dependencies
                if self._prompt(
                    "Keeps dependencies in <b>[tool.poetry]</b>?",
                    additional_info=(
                        "<b>[tool.poetry.dependencies]</b> found. "
                        "`dependencies` will be added to <b>[project.dynamic]</b> "
                        "if you want to keep it in <b>[tool.poetry]</b>. "
                    ),
                ):
                    add_dynamic("dependencies")
                else:
                    # Move dependencies to [project] and remove from [tool.poetry]
                    if "dependencies" not in project:
                        project["dependencies"] = array()
                    project_dependencies: list[str] = project["dependencies"]

                    project_dependencies_objs = [
                        Dependency.create_from_pep_508(constraint)
                        for constraint in project_dependencies
                    ]

                    def transform_dependency_item(
                        orig_name: str, tool_poetry_dependencies: dict[str, Any]
                    ):
                        constraint = tool_poetry_dependencies[orig_name]

                        if orig_name.startswith(MULTIPLE_CONSTRAINT_TEMP_NAME_PREFIX):
                            name = orig_name.split("$")[1]
                        else:
                            name = orig_name

                        dependency = Factory.create_dependency(name, constraint)
                        if dependency.name == "python" or (
                            isinstance(dependency, PathDependency)
                            and not dependency.path.is_absolute()
                        ):
                            # Skip if dependency is Python itself or if its path is relative
                            raise SkipField()

                        if any(
                            project_dependency.name == dependency.name
                            for project_dependency in project_dependencies_objs
                        ):
                            self.warnings.append(
                                f"Dependency {dependency} is already defined in "
                                "<b>[project.dependencies]</b> and it will be skipped."
                            )
                            raise SkipField()

                        # Removes fields that can be presented with pep-508 str from constraint
                        remove_fields_from_constraint(
                            constraint,
                            ["optional"],
                            # keep markers for expanded dependencies
                            include_markers=not orig_name.startswith(
                                MULTIPLE_CONSTRAINT_TEMP_NAME_PREFIX
                            ),
                        )

                        if dependency.is_optional():
                            if len(constraint) == 0:
                                # Remove from [tool.poetry.dependencies] if only optional
                                del tool_poetry_dependencies[orig_name]
                            raise SkipField()

                        # Check if there's any field left in constraint
                        if len(constraint) == 0 or isinstance(constraint, str):
                            # Just return, it will be moved from [tool.poetry.dependencies]
                            return string(dependency.to_pep_508(), literal=self.literal)
                        else:
                            # Its new value needs to be kept in [tool.poetry.dependencies]
                            # while other parts that can be presented with pep-508 str
                            # will be moved to [project]
                            raise CopyModifiedField(
                                string(dependency.to_pep_508(), literal=self.literal),
                                constraint,
                            )

                    self._move_sub_container(
                        "dependencies",
                        tool_poetry,
                        project_dependencies,
                        from_container_key="tool.poetry",
                        to_container_key="project.dependencies",
                        from_item_transformer=transform_dependency_item,
                    )

                # Rebuild multiple constraints
                for package_name in tuple(tool_poetry_dependencies.keys()):
                    if package_name.startswith(MULTIPLE_CONSTRAINT_TEMP_NAME_PREFIX):
                        constraint = tool_poetry_dependencies[package_name]
                        original_package_name = package_name.split("$")[1]
                        if original_package_name not in tool_poetry_dependencies:
                            tool_poetry_dependencies[original_package_name] = array()
                        target_constraints: list = tool_poetry_dependencies[
                            original_package_name
                        ]
                        target_constraints.append(constraint)
                        del tool_poetry_dependencies[package_name]

        # Other changes
        ## requires-poetry
        if "requires-poetry" not in tool_poetry:
            target_constraint = self._select_constraint("tool.poetry.requires-poetry")
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
            )
            if target_constraint:
                if not constraint.intersect(target_constraint).is_empty():
                    # Update only if selected constraint is compatible with current value
                    tool_poetry["requires-poetry"] = string(
                        str(target_constraint), literal=self.literal
                    )
                else:
                    self.warnings.append(
                        "Not updating [tool.poetry.requires-poetry] "
                        f"since current value {constraint} is not compatible with {target_constraint}."
                    )

        ## build-system.requires
        if "build-system" in new_document:
            build_system = new_document["build-system"]
            if "requires" in build_system:
                requires = build_system["requires"]
                for i, requirement in enumerate(requires):
                    dependency = Dependency.create_from_pep_508(requirement)
                    if dependency.name == "poetry-core":
                        constraint = dependency.constraint
                        if constraint.is_any():
                            # Only ask for updating it when no constraint is set
                            target_constraint = self._select_constraint(
                                "build-system.requires.poetry-core"
                            )
                            if target_constraint:
                                dependency.constraint = target_constraint  # type: ignore[assignment]
                                requires[i] = string(
                                    dependency.to_pep_508(), literal=self.literal
                                )
                            break

        return new_document  # type: ignore[return-value]
