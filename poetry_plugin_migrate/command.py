from __future__ import annotations

from typing import TYPE_CHECKING

from cleo.helpers import option
from poetry.console.commands.command import Command

from poetry_plugin_migrate.migrator import Migrator

if TYPE_CHECKING:
    from typing import Callable

    from tomlkit.items import Item

    ItemTransformer = (
        Callable[[str, dict[str, Item]], Item] | Callable[[int, list[Item]], Item]
    )


class MigrateCommand(Command):
    name = "migrate"
    description = (
        "Migrate <comment>pyproject.toml</comment> "
        "from Poetry v1 to v2 (PEP-621 compliant)."
    )

    options = [
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
            description="Do not create a backup of <comment>pyproject.toml</comment> before migration.",
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
            description="Use basic strings instead of literal strings in <comment>pyproject.toml</comment>.",
        ),
    ]

    def handle(self):
        no_check = self.option("no-check")
        dry_run = self.option("dry-run")
        quiet = self.option("quiet")
        no_interaction = self.option("no-interaction")
        no_literal = self.option("no-literal")

        if not no_check:
            # Run `poetry check` to ensure pyproject.toml is valid
            check_strict = self.option("check-strict")

            self.write(
                (
                    "\n<b>Checking</> the current project:"
                    f" <c1>{self.poetry.package.pretty_name}</c1>"
                    f" (<c2>{self.poetry.package.pretty_version}</c2>)\n"
                )
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

        no_backup = self.option("no-backup")
        if not no_backup and not dry_run:
            # Create a backup of pyproject.toml
            pyproject_backup_file_path = pyproject_file_path.parent / (
                pyproject_file_path.stem + ".bak" + pyproject_file_path.suffix
            )
            self.line(f"Creating backup at <c1>{pyproject_backup_file_path}</>")
            self.line("")
            pyproject_backup_file_path.write_text(self.poetry.file.path.read_text())

        self.line("Migrating <comment>pyproject.toml</comment>...")
        self.line("")
        migrator = Migrator(
            command=self,
            skip=quiet or no_interaction,
            literal=not no_literal,
        )
        pyproject_document = self.poetry.pyproject.data
        migrated_document = migrator.run(pyproject_document)

        if len(migrator.warnings) > 0:
            for warning in migrator.warnings:
                self.line_error(f"<warning>Warning: {warning}</warning>")
            self.line("")

        self.line("<info>Generated file</info>")
        self.line("")

        if dry_run:
            self.line(migrated_document.as_string())
        else:
            from poetry.toml import TOMLFile

            self.line("<info>Writing <comment>pyproject.toml</comment></info>")
            self.line("")

            migrated_file = TOMLFile(pyproject_file_path)
            migrated_file.write(migrated_document)

            self.line(
                "It is recommended to run <info>poetry lock && poetry install</info> after migration."
            )
