from __future__ import annotations

from typing import TYPE_CHECKING

from cleo.helpers import option
from poetry.console.commands.command import Command

from poetry_plugin_migrate.migrator import Migrator

if TYPE_CHECKING:
    from typing import ClassVar

    from cleo.io.inputs.option import Option


class MigrateCommand(Command):
    name = "migrate"
    description: str = (
        "Migrate <comment>pyproject.toml</comment> "
        "from Poetry v1 to v2 (PEP-621 compliant)."
    )

    options: ClassVar[list[Option]] = [
        option(
            long_name="no-check",
            short_name=None,
            description="Skip <info>poetry check</info> for <comment>pyproject.toml</comment>.",
        ),
        option(
            long_name="check-strict",
            short_name=None,
            description="Fail if check reports warnings.",
        ),
        option(
            long_name="no-backup",
            short_name=None,
            description=(
                "Do not create a backup of <comment>pyproject.toml</comment> "
                "before writing the migrated file."
            ),
        ),
        option(
            long_name="dry-run",
            short_name=None,
            description=(
                "Run the migration without modifying the <comment>pyproject.toml</comment>. "
                "Migration result will be printed to the console."
            ),
        ),
        option(
            long_name="no-literal",
            short_name=None,
            description=(
                "Use TOML basic strings for generated requirements and "
                "constraint values instead of preferring literal strings."
            ),
        ),
    ]

    def handle(self) -> int:
        no_check = self.option("no-check")
        dry_run = self.option("dry-run")
        quiet = self.option("quiet")
        no_interaction = self.option("no-interaction")
        no_literal = self.option("no-literal")

        if not no_check:
            # Run `poetry check` to ensure pyproject.toml is valid
            check_strict = self.option("check-strict")

            self.write(
                "\n<b>Checking</> the current project:"
                f" <c1>{self.poetry.package.pretty_name}</c1>"
                f" (<c2>{self.poetry.package.pretty_version}</c2>)\n"
            )
            self.line("")

            ret = self.call("check", "--strict" if check_strict else None)
            self.line("")
            if ret != 0:
                self.line_error(
                    "<error>Migration aborted due to errors in pyproject.toml.</error>"
                )
                return ret

        pyproject_file_path = self.poetry.file.path

        self.line("Migrating <comment>pyproject.toml</comment>...")
        self.line("")
        migrator = Migrator(
            command=self,
            skip=quiet or no_interaction,
            literal=not no_literal,
        )
        pyproject_document = self.poetry.pyproject.data
        try:
            migrated_document = migrator.run(pyproject_document)
        except (TypeError, ValueError) as error:
            self.line_error(f"<error>Migration aborted: {error}</error>")
            return 1

        from poetry.core.factory import Factory as CoreFactory

        validation = CoreFactory.validate(migrated_document.unwrap(), strict=True)
        if validation["errors"]:
            self.line_error(
                "<error>Migration aborted because the generated configuration "
                "is invalid:</error>"
            )
            for validation_error in validation["errors"]:
                self.line_error(f"  - {validation_error}")
            return 1

        if len(migrator.warnings) > 0:
            for warning in migrator.warnings:
                self.line_error(f"<warning>Warning: {warning}</warning>")
            self.line("")

        if (
            not dry_run
            and migrated_document.as_string() == pyproject_document.as_string()
        ):
            self.line("<info>No migration changes were necessary.</info>")
            return 0

        self.line("<info>Generated file</info>")
        self.line("")

        if dry_run:
            self.line(migrated_document.as_string())
        else:
            from shutil import copy2

            from poetry.toml import TOMLFile

            no_backup = self.option("no-backup")
            if not no_backup:
                backup = pyproject_file_path.with_name(
                    f"{pyproject_file_path.stem}.bak{pyproject_file_path.suffix}"
                )
                index = 1
                while backup.exists():
                    backup = pyproject_file_path.with_name(
                        f"{pyproject_file_path.stem}.bak.{index}"
                        f"{pyproject_file_path.suffix}"
                    )
                    index += 1
                self.line(f"Creating backup at <c1>{backup}</>")
                self.line("")
                copy2(pyproject_file_path, backup)

            self.line("<info>Writing <comment>pyproject.toml</comment></info>")
            self.line("")

            migrated_file = TOMLFile(pyproject_file_path)
            migrated_file.write(migrated_document)

            self.line(
                "It is recommended to run <info>poetry lock && poetry install</info> after migration."
            )

        return 0
