from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import TypeAlias, TypeGuard

from tomlkit import TOMLDocument, string
from tomlkit.container import Container, OutOfOrderTableProxy
from tomlkit.exceptions import InvalidStringError
from tomlkit.items import (
    AbstractTable,
    AoT,
    Array,
    Comment,
    Item,
    Key,
    Null,
    String,
    Table,
    Trivia,
    Whitespace,
)

TomlTable: TypeAlias = AbstractTable | OutOfOrderTableProxy
BodyEntry: TypeAlias = tuple[Key | None, Item]
DocumentBlock: TypeAlias = tuple[str, list[BodyEntry]]


def make_string(value: str, *, literal: bool) -> String:
    """Create a TOML string, falling back when literal syntax cannot encode it."""
    try:
        return string(value, literal=literal)
    except InvalidStringError:
        if not literal:
            raise
        return string(value, literal=False)


def _collect_item_comments(
    item: Item, result: Counter[str], *, include_trivia: bool = True
) -> None:
    if isinstance(item, Comment) or (
        include_trivia and not isinstance(item, Whitespace) and item.trivia.comment
    ):
        result[item.trivia.comment] += 1

    if isinstance(item, AbstractTable):
        _collect_comments(item.value, result)
    elif isinstance(item, AoT):
        for table_item in item:
            _collect_comments(table_item.value, result)
    elif isinstance(item, Array):
        # Public list iteration exposes only values. tomlkit's item iterator
        # additionally includes standalone comments and whitespace groups.
        # Array serialization ignores trivia attached to a value item, so only
        # explicit Comment groups count as retained at this level.
        for array_item in item._iter_items():
            _collect_item_comments(array_item, result, include_trivia=False)


def _collect_comments(container: Container, result: Counter[str]) -> None:
    for _key, item in container.body:
        _collect_item_comments(item, result)


def comment_counts(document: TOMLDocument) -> Counter[str]:
    """Count standalone and inline comments throughout a TOML document."""
    result: Counter[str] = Counter()
    _collect_comments(document, result)
    return result


def restore_missing_comments(
    document: TOMLDocument, expected: Counter[str]
) -> list[str]:
    """Append comments lost with removed tomlkit items and return their texts.

    tomlkit associates comments between sections with one of the parsed tables.
    Removing that table can therefore remove the comment as well. Its intended
    destination is unknowable, so retain the text at the end of the document
    instead of silently discarding it.
    """
    missing = expected - comment_counts(document)
    restored: list[str] = []
    for text, count in missing.items():
        for _ in range(count):
            document.add(Comment(Trivia(comment=text)))
            restored.append(text)
    return restored


def append_array_value(target: Array, value: Item, source: Item) -> None:
    """Append a value while preserving an exact source inline comment.

    ``Array.add_line(comment=...)`` always normalizes comment spacing.  Assign
    the parsed comment trivia to the new array group instead so forms such as
    ``#tight`` and ``## heading`` remain byte-for-byte unchanged.
    """
    target.add_line(value)
    if not source.trivia.comment:
        return

    group = target._value[target._index_map[len(target) - 1]]
    group.comment = Comment(
        Trivia(
            indent=source.trivia.comment_ws,
            comment=source.trivia.comment,
            trail="",
        )
    )


def extend_array_preserving_comments(
    target: Array, source: Array, replacements: list[Item]
) -> None:
    """Append transformed values with their parsed array comment groups.

    tomlkit's public Array API exposes values but not the standalone and inline
    comments grouped around each value.  Copying its parsed groups is therefore
    required to retain comments beside multiple-constraint branches.
    """
    if len(source) != len(replacements):
        raise ValueError("Every source array value requires one replacement")

    transformed = deepcopy(source)
    for index, replacement in enumerate(replacements):
        # Replacing through Array.__setitem__ transfers formatting from the
        # scalar source value into the replacement (for example, it removes
        # spaces inside a generated inline table). Replace only the parsed
        # group's value so the surrounding array trivia is retained while the
        # generated item's own formatting remains intact.
        group = transformed._value[transformed._index_map[index]]
        group.value = replacement

    if target._value and isinstance(target._value[-1].value, Null):
        target._value.pop()
    list.extend(target, replacements)
    target._value.extend(transformed._value)
    target._reindex()


def _reorder_tool_namespace(
    blocks: list[DocumentBlock],
) -> tuple[list[DocumentBlock], bool]:
    """Put all ``tool.poetry`` table blocks before other tool tables.

    A parsed document can contain several physical ``tool`` super-tables when
    unrelated top-level tables interrupt its declarations. Combine those
    containers so the stable partition applies across the complete namespace,
    while retaining the order within the Poetry and non-Poetry partitions.
    """
    tool_blocks = [block for block in blocks if block[0] == "tool"]
    if not tool_blocks:
        return blocks, False

    namespace_preamble: list[BodyEntry] = []
    namespace_blocks: list[DocumentBlock] = []
    document_tail: list[BodyEntry] = []
    outer_tables: list[tuple[Key, Table]] = []

    for _, entries in tool_blocks:
        outer_key, outer_item = entries[0]
        if outer_key is None or not isinstance(outer_item, Table):
            raise TypeError("[tool] must be represented by a TOML table")
        outer_tables.append((outer_key, outer_item))
        document_tail.extend(entries[1:])

        current_block: list[BodyEntry] | None = None
        for key, item in outer_item.value.body:
            entry = (key, item)
            if isinstance(item, (AbstractTable, AoT)) and key is not None:
                current_block = [entry]
                namespace_blocks.append((key.key, current_block))
            elif current_block is not None:
                current_block.append(entry)
            else:
                # Values declared directly in an explicit [tool] table, plus
                # its comments and whitespace, remain a namespace preamble.
                namespace_preamble.append(entry)

    ordered_namespace_blocks = [
        *(block for block in namespace_blocks if block[0] == "poetry"),
        *(block for block in namespace_blocks if block[0] != "poetry"),
    ]
    namespace_reordered = [name for name, _ in ordered_namespace_blocks] != [
        name for name, _ in namespace_blocks
    ]
    if len(tool_blocks) == 1 and not namespace_reordered:
        return blocks, False

    # An explicit [tool] declaration owns namespace-level values and must be
    # retained if present. Otherwise any super-table is a suitable shell.
    base_key, base_table = next(
        ((key, item) for key, item in outer_tables if not item.is_super_table()),
        outer_tables[0],
    )
    combined_table = Table(
        Container(parsed=True),
        deepcopy(base_table.trivia),
        base_table.is_aot_element(),
        is_super_table=base_table.is_super_table(),
        name=base_table.name,
        display_name=base_table.display_name,
    )
    namespace_block_written = False
    serialized_tail = ""
    for key, item in [
        *namespace_preamble,
        *(entry for _, block in ordered_namespace_blocks for entry in block),
    ]:
        copied_item = deepcopy(item)
        if isinstance(copied_item, (Table, AoT)):
            if (
                namespace_block_written
                and not serialized_tail.endswith("\n\n")
                and "\n" not in copied_item.trivia.indent
            ):
                copied_item.trivia.indent = "\n"
            namespace_block_written = True
        combined_table.value._raw_append(deepcopy(key), copied_item)
        serialized_tail = (serialized_tail + copied_item.as_string())[-2:]

    combined_block: DocumentBlock = (
        "tool",
        [(deepcopy(base_key), combined_table), *document_tail],
    )
    result: list[DocumentBlock] = []
    inserted = False
    for block in blocks:
        if block[0] != "tool":
            result.append(block)
        elif not inserted:
            result.append(combined_block)
            inserted = True
    return result, True


def reorder_standard_tables(document: TOMLDocument) -> TOMLDocument:
    """Return a document with standardized top-level tables in canonical order.

    TOML and the packaging specifications do not assign semantic meaning to
    table order. This optional layout keeps each parsed top-level table intact,
    including the comments and whitespace tomlkit stores inside that table. It
    deliberately does not reorder keys, nested tables, groups, or arrays.
    """
    preamble: list[BodyEntry] = []
    blocks: list[DocumentBlock] = []

    for key, item in document.body:
        entry = (key, item)
        if isinstance(item, (AbstractTable, AoT)) and key is not None:
            blocks.append((key.key, [entry]))
        elif blocks:
            # Root-level trivia following a table stays with that table. Most
            # inter-table comments are already contained by the preceding
            # parsed Table, but retaining this tail also covers manually built
            # TOMLDocument instances without interpreting comment semantics.
            blocks[-1][1].append(entry)
        else:
            preamble.append(entry)

    blocks, tool_reordered = _reorder_tool_namespace(blocks)

    def rank(name: str) -> int:
        if name == "project":
            return 0
        if name == "dependency-groups":
            return 1
        if name == "tool":
            return 2
        if name == "build-system":
            return 4
        return 3

    ordered_blocks = sorted(blocks, key=lambda block: rank(block[0]))
    if not tool_reordered and [name for name, _ in ordered_blocks] == [
        name for name, _ in blocks
    ]:
        return document

    result = TOMLDocument(parsed=True)
    ordered_entries = [
        *preamble,
        *(entry for _, block in ordered_blocks for entry in block),
    ]
    first_table_written = False
    serialized_tail = ""
    for key, item in ordered_entries:
        copied_item = deepcopy(item)
        if isinstance(copied_item, (Table, AoT)):
            if not first_table_written:
                # A parsed table's indent separates it from its old
                # predecessor. At the front of the reordered table sequence,
                # the document preamble already carries its own exact trailing
                # whitespace.
                copied_item.trivia.indent = ""
                first_table_written = True
            elif (
                not serialized_tail.endswith("\n\n")
                and "\n" not in copied_item.trivia.indent
            ):
                # The old predecessor can own the separating whitespace in
                # tomlkit's parsed model. Ensure reordered top-level blocks do
                # not run together, without removing any existing whitespace.
                copied_item.trivia.indent = "\n"
        # Public append() merges repeated super-tables such as two [tool.*]
        # blocks separated in the source. Raw append retains those physical
        # blocks and lets tomlkit expose them through OutOfOrderTableProxy,
        # preserving section-local comments instead of moving them during a
        # merge.
        result._raw_append(deepcopy(key), copied_item)
        serialized_tail = (serialized_tail + copied_item.as_string())[-2:]
    return result


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
