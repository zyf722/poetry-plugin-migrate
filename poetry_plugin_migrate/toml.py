from __future__ import annotations

from typing import TypeAlias, TypeGuard

from tomlkit.container import OutOfOrderTableProxy
from tomlkit.items import AbstractTable, Array, Item

TomlTable: TypeAlias = AbstractTable | OutOfOrderTableProxy


def is_table(value: object) -> TypeGuard[TomlTable]:
    """Return whether a parsed TOML value behaves as a table."""
    return isinstance(value, (AbstractTable, OutOfOrderTableProxy))


def require_table(value: object, path: str) -> TomlTable:
    """Narrow a parsed TOML value to a table or fail with useful context."""
    if not isinstance(value, (AbstractTable, OutOfOrderTableProxy)):
        raise TypeError(f"[{path}] must be a table, got {type(value).__name__}")
    return value


def require_array(value: object, path: str) -> Array:
    """Narrow a parsed TOML value to an array or fail with useful context."""
    if not isinstance(value, Array):
        raise TypeError(f"[{path}] must be an array, got {type(value).__name__}")
    return value


def require_item(value: object, path: str) -> Item:
    """Narrow a parsed TOML value to a trivia-bearing item."""
    if not isinstance(value, Item):
        raise TypeError(f"[{path}] must be a TOML item, got {type(value).__name__}")
    return value
