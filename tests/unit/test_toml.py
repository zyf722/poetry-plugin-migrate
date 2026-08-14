from __future__ import annotations

from collections import Counter

import pytest
from tomlkit import TOMLDocument, parse

from poetry_plugin_migrate.migrator import Migrator
from poetry_plugin_migrate.toml import (
    comment_counts,
    make_string,
    restore_missing_comments,
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


def migrate(source: str) -> tuple[TOMLDocument, Migrator]:
    migrator = Migrator(StubCommand(), skip=True, literal=False)
    return migrator.run(parse(source)), migrator


def test_removed_items_do_not_silently_drop_comments() -> None:
    source = """\
# document note
[tool.poetry]
# name note
name = "dummy-comments"
version = "1.0.0" # version note

# unrelated table note
[tool.synthetic]
enabled = true

# dependencies table note
[tool.poetry.dependencies]
python = ">=3.10" # python note
dummy = "^1" # dependency note
"""
    original_comments = comment_counts(parse(source))

    result, _ = migrate(source)

    assert comment_counts(result) >= original_comments
    parse(result.as_string())


def test_comments_inside_removed_arrays_are_restored() -> None:
    source = """\
[tool.poetry]
name = "dummy-array-comments"
version = "1.0.0"
authors = [
    # primary author note
    "Dummy Author <dummy@example.invalid>", # inline author note
    # duplicate author has no unique generated destination
    "Dummy Author <dummy@example.invalid>",
]
"""
    original_comments = comment_counts(parse(source))

    result, migrator = migrate(source)

    assert comment_counts(result) >= original_comments
    assert any("Restored" in warning for warning in migrator.warnings)
    parse(result.as_string())


def test_comments_in_one_to_one_person_arrays_stay_with_generated_people() -> None:
    source = """\
[tool.poetry]
name = "dummy-person-comments"
version = "1.0.0"
authors = [
    # primary author note
    "Dummy Author <dummy@example.invalid>", # inline author note
]
"""

    result, migrator = migrate(source)

    rendered = result.as_string()
    assert "# primary author note" in rendered
    assert "# inline author note" in rendered
    assert not any("Restored" in warning for warning in migrator.warnings)


@pytest.mark.parametrize(
    "source_comment",
    ["#tight", "## heading", "#", "#   spaced"],
)
def test_restored_comment_text_is_exact(source_comment: str) -> None:
    result = parse("value = 1\n")

    restored = restore_missing_comments(result, Counter({source_comment: 1}))

    assert restored == [source_comment]
    assert result.as_string().splitlines()[-1] == source_comment


def test_literal_string_factory_falls_back_to_basic_toml_syntax() -> None:
    value = "text containing an apostrophe: owner's"
    generated = make_string(value, literal=True)

    assert parse(f"value = {generated.as_string()}\n")["value"] == value
