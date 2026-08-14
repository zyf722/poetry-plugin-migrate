# Poetry Plugin: Migrate

[![License](https://img.shields.io/github/license/zyf722/poetry-plugin-migrate)](LICENSE)
[![PyPI version](https://img.shields.io/pypi/v/poetry-plugin-migrate?logo=pypi&logoColor=white&label=PyPI)](https://pypi.org/project/poetry-plugin-migrate/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/poetry-plugin-migrate?logo=python&logoColor=white&label=Python)](https://pypi.org/project/poetry-plugin-migrate/)
[![Poetry version](https://img.shields.io/badge/Poetry-%3E%3D2.2.1-blue?logo=poetry&logoColor=white)](https://python-poetry.org/)
[![Github Actions Build](https://img.shields.io/github/actions/workflow/status/zyf722/poetry-plugin-migrate/build.yml?logo=github)](https://github.com/zyf722/poetry-plugin-migrate/actions/workflows/build.yml)
[![Code Coverage](https://img.shields.io/codecov/c/github/zyf722/poetry-plugin-migrate?logo=codecov&logoColor=white
)](https://app.codecov.io/github/zyf722/poetry-plugin-migrate/)

This package is a plugin that helps you migrate `pyproject.toml` of your Poetry v1 project to the v2 recommended format, which follows the specification on the [PyPA specs page](https://packaging.python.org/en/latest/specifications/pyproject-toml/#pyproject-toml-spec) (originally defined by [PEP-621](https://peps.python.org/pep-0621/)).

Check the blog post by Poetry team for more details: [Announcing Poetry 2.0.0 # Supporting the project section in pyproject.toml (PEP 621)](https://python-poetry.org/blog/announcing-poetry-2.0.0/#supporting-the-project-section-in-pyprojecttoml-pep-621).

## Installation

The easiest way to add the `migrate` plugin is via the `self add` command of Poetry.

```bash
poetry self add poetry-plugin-migrate
```

If you used `pipx` to install Poetry you can add the plugin via the `pipx inject` command.

```bash
pipx inject poetry poetry-plugin-migrate
```

Otherwise, if you used `pip` to install Poetry you can add the plugin packages via the `pip install` command.

```bash
pip install poetry-plugin-migrate
```


## Usage

The plugin provides a `migrate` command to migrate the current `pyproject.toml` to the new format.

Start with a dry run and inspect the output before writing the file:

```bash
poetry migrate --dry-run
```

Then run the migration, validate the result, and review the diff:

```bash
poetry migrate
poetry lock
poetry check --strict
git diff -- pyproject.toml poetry.lock
```

By default, the command performs a `poetry check` before migration and then attempts to migrate the current `pyproject.toml` based on several [rules](#migration-rules) and the user's responses to interactive prompts. The generated document is validated against Poetry's schemas before any file is written. A backup is created only after migration and validation succeed. Existing backups are never overwritten: after `pyproject.bak.toml`, the command uses `pyproject.bak.1.toml`, `pyproject.bak.2.toml`, and so on. If migration makes no changes, a normal run creates no backup and does not rewrite the file; `--dry-run` still prints the unchanged result.

The final interactive prompt optionally applies a canonical top-level layout. It is disabled by default, including in `--no-interaction` mode. Neither the [TOML specification](https://toml.io/en/v1.0.0#table) nor the Python packaging specifications ([project metadata](https://packaging.python.org/en/latest/specifications/pyproject-toml/) and [dependency groups](https://packaging.python.org/en/latest/specifications/dependency-groups/)) define a semantic or recommended table order; this is a formatting convention used by this plugin:

1. `[project]`
2. `[dependency-groups]`
3. the `[tool]` namespace, with all `[tool.poetry]` and `[tool.poetry.*]` tables before other tool tables
4. other top-level tables, retaining their relative order
5. `[build-system]`

Only complete table blocks are reordered. Within the `[tool]` namespace, Poetry table blocks are moved before other tools; Poetry blocks retain their relative order, and all non-Poetry tool blocks retain their relative order. Fields within `[project]`, dependency group names, requirement arrays, nested tables, and tool-specific configuration retain their existing order. In particular, dependency arrays are never alphabetized or deduplicated.

tomlkit preserves adjacent comments and blank lines, representing blank lines as separate whitespace items, but it does not determine whether a comment was intended to describe the preceding or following section. In particular, a comment between two top-level table headers is normally stored in the preceding parsed table even if a blank line appears before the comment; the blank line is preserved but does not change that association. When canonical layout is selected, the plugin moves the complete physical table block that tomlkit parsed, together with the comments and whitespace stored in that block; the document preamble remains at the beginning. The plugin does not apply its own comment-ownership heuristic, so a comment between reordered sections can move with the preceding parsed table.

This ownership limitation also applies when canonical layout is disabled: migration itself moves and removes legacy fields and tables. Inline and standalone comments inside dependency arrays, including multiple-constraint branches, remain with their generated requirement whenever tomlkit exposes their parsed association. If one optional dependency is emitted into several extras, its source comment stays with the first generated occurrence instead of being duplicated. The plugin also counts exact comment text before and after migration; if a removed source structure provides no destination association, the original comment token (including its `#` spelling and spacing after `#`) is restored at the end of the document and a warning asks you to review its placement. This prevents silent text loss but cannot infer where an inter-section or container-level comment belongs. Always review comment placement in the diff. The default layout-preserving behavior avoids the additional whole-table reordering only. Physically split `[tool.poetry]` declarations are consolidated only when migration may need to edit them; inspection alone leaves their layout unchanged.

For readability, generated requirements, license expressions, and version constraints prefer TOML literal strings. Literal syntax cannot represent a single quote in a single-line value, so such a value automatically falls back to an escaped TOML basic string. Values moved unchanged retain their original TOML syntax; structural strings generated inside people tables, dynamic field lists, and include-group objects use tomlkit's basic-string default. `--no-literal` selects basic strings for the requirement and constraint values that would otherwise prefer literal syntax; it does not reserialize the whole document.

> **Note**: Internally, this plugin uses [`tomlkit`](https://github.com/python-poetry/tomlkit), a *style-preserving* TOML library, to parse and modify the `pyproject.toml` file. Hence, the migrated result might NOT be pretty-formatted and might need reformatting.

### Available Options
- `-n` / `--no-interaction`: Skip interactive prompts and use default migration strategies. This is a global Poetry option.
- `--no-check`: Skip `poetry check` for `pyproject.toml`.
- `--check-strict`: Fail if check reports warnings.
- `--no-backup`: Do not create a backup of `pyproject.toml` before migration.
- `--dry-run`: Run the migration without modifying the `pyproject.toml`. Migration result will be printed to the console.
- `--no-literal`: Use TOML basic strings for generated requirements and constraint values instead of preferring literal strings.

## Migration Rules

### Directly-Migrated Fields
Following fields will be directly migrated:

| Before | After | Notes |
| :---: | :---: | :---: |
| `[tool.poetry.name]` | `[project.name]` | - |
| `[tool.poetry.description]` | `[project.description]` | - |
| `[tool.poetry.license]` | `[project.license]` | Moved only if it is already a valid SPDX expression; legacy license text is kept dynamic for manual migration |
| `[tool.poetry.keywords]` | `[project.keywords]` | - |
| `[tool.poetry.urls]` | `[project.urls]` | Moved only when `[project.urls]` does not already exist |
| `[tool.poetry.homepage]` | `[project.urls.homepage]` | - |
| `[tool.poetry.repository]` | `[project.urls.repository]` | - |
| `[tool.poetry.documentation]` | `[project.urls.documentation]` | - |
| `[tool.poetry.plugins]` | `[project.entry-points]` | Moved only when `[project.entry-points]` does not already exist |
| `[tool.poetry.scripts]` | `[project.scripts]` | Moved only when `[project.scripts]` does not already exist, and only for entries that are **NOT** of type `file` <br> See python-poetry/poetry#9510 for details |
| `[tool.poetry.authors]` | `[project.authors]` | Format changed from `"name <email>"` to `{"name": name, "email": email}` |
| `[tool.poetry.maintainers]` | `[project.maintainers]` | Format changed from `"name <email>"` to `{"name": name, "email": email}` |
| `[tool.poetry.extras]` | `[project.optional-dependencies]` | See [Dependencies Migration](#dependencies-migration) for details |

An existing standardized value is authoritative. Equal scalar duplicates can be removed, but a different legacy scalar is retained with a warning. Existing container-valued metadata—URLs, entry points, scripts, classifiers, readme declarations, authors, and maintainers—is not extended from legacy declarations, because Poetry already treats the standard container as effective metadata and merging ignored legacy values would silently change the wheel. If migration itself makes a field static while it was dynamic, the newly conflicting dynamic name is removed with a warning. Pre-existing static/dynamic conflicts unrelated to migration are not silently repaired; the command's validation instead reports them.

### Conditional-Migrated Fields
Fields below either need the user to choose migration strategies for them, or are migrated only under specific conditions.

The option marked with `(*)` is the default choice.

#### `[tool.poetry.version]`
You can **choose** one of the following strategies for this field:

- (*) move it to `[project]`
- or, keep it in `[tool.poetry]`

If you want to set the version dynamically via `poetry build --local-version` or you are using a plugin which sets the version dynamically, you should use *dynamic versioning* that keeps it in `[tool.poetry]` and adds `"version"` to `[project.dynamic]`.

Otherwise, this field will be moved to `[project]`.

#### `[tool.poetry.license]`

A license value is moved to `[project.license]` only when it is already a valid SPDX license expression, such as `MIT` or `MIT OR Apache-2.0`; identifier and operator casing is normalized by `packaging`. PEP 639 does not allow a migration tool to infer a License-Expression from ambiguous legacy license text without explicit user confirmation. Values such as `MIT License` or project-specific license descriptions are therefore kept in `[tool.poetry.license]`, while `"license"` is added to `[project.dynamic]` and a warning requests manual review. The plugin does not maintain a hard-coded alias table or guess an SPDX identifier.

#### `[tool.poetry.readme]`
The migration strategy for this field depends on its value:

- If the value is a single string (one file), it will be moved to `project.readme`.
- Otherwise (multiple files), it will be kept in `[tool.poetry]` and `"readme"` will be added to `[project.dynamic]`.

#### `[tool.poetry.classifiers]`
You can **choose** one of the following strategies for this field:

- (*) keep it in `[tool.poetry]`
- or, move it to `[project]`

Per default Poetry determines classifiers for supported Python versions and license automatically.

If you define classifiers in `[project]`, you disable the automatic enrichment. In other words, you have to define all classifiers manually.

If you want to use Poetry's automatic enrichment of classifiers, they should be kept in [tool.poetry] and 'classifiers' should be added to `[project.dynamic]`.

#### `[tool.poetry.dependencies.python]`
You can **choose** one of the following strategies for this field:

- Move to `[project.requires-python]`
- Add `requires-python` to `[project.dynamic]`
- (*) Copy value to `[project.requires-python]`
- No migration and keep it as-is

See [Poetry documentation](https://python-poetry.org/docs/main/pyproject/#requires-python) for further information about this field.

Poetry accepts some constraints that the standardized `requires-python` field cannot express, including union constraints using `||` and local-version comparisons in otherwise invalid specifier positions. Such a value is kept under `[tool.poetry.dependencies.python]`, `requires-python` is marked dynamic, and a warning is emitted instead of writing invalid project metadata.

#### `[tool.poetry.dependencies]`
For dependencies, you can **choose** one of the following strategies:

- keep it in `[tool.poetry]`
- (*) or, move it to `[project]`

See [Dependencies Migration](#dependencies-migration) for details on how dependencies are migrated if you choose to move them to `[project]`.

#### `[tool.poetry.requires-poetry]`
You can explicitly specify the required Poetry version in `[tool.poetry.requires-poetry]` since Poetry v2. Following constraints are available for you to **choose**:

- `>=2.2.1`
- `>=2.2.1,<3.0.0`
- (*) No update

#### `[build-system.requires]`
You can also **choose** one of the following constraints of `poetry-core` for building:

- `>=2.0`
- `>=2.0,<3.0`
- `>=2.0.0`
- `>=2.0.0,<3.0.0`
- (*) No update

### Dependencies Migration
Entries in `[tool.poetry.dependencies]` and `[tool.poetry.extras]` will be migrated to [PEP-508](https://peps.python.org/pep-0508/) strings in `[project.dependencies]` and `[project.optional-dependencies]` respectively.

Existing non-empty standardized dependency containers are authoritative. If `[project.dependencies]` already contains entries while legacy non-Python dependencies also exist, or a non-empty `[project.optional-dependencies]` coexists with legacy extras, migration aborts instead of guessing how two authoritative models should be merged. An explicitly empty array or table is treated as a migration placeholder and populated. Dependency and extra names are matched using normalized Python package names; duplicate names that normalize to the same value also abort. An optional dependency may be shared by multiple extras and is rendered independently into every corresponding standardized extra.

Some dependency semantics cannot be represented completely in PEP-508 project metadata. These include relative paths, Poetry-only fields such as `source`, `allow-prereleases`, or `develop`, and version unions such as `>=1,<2 || >=3,<4`. Every generated requirement is parsed by both `packaging` and Poetry and must round-trip without changing its constraint, extras, markers, or direct-reference source. The one deliberate round-trip exception is a wheel URL: Poetry can infer a version constraint from the `.whl` filename even though a PEP-508 direct URL identifies the artifact without a separate constraint. This exception applies only to unconstrained URL dependencies whose URL path ends in `.whl`; source URL, extras, markers, and all other direct-reference fields must still match.

If any non-Python main dependency fails this check, the plugin keeps the complete non-Python `[tool.poetry.dependencies]` and `[tool.poetry.extras]` model together and adds `"dependencies"` to `[project.dynamic]`. This is intentionally all-or-nothing: once `[project.dependencies]` exists, Poetry treats it as the authoritative main dependency model and does not merge arbitrary legacy-only entries back into wheel metadata. Migrating safe entries while leaving one private-source or relative-path entry under Poetry would therefore make that retained entry disappear from the built package. The separate Python constraint choice is applied before this safety check, so `[tool.poetry.dependencies.python]` is retained, copied, moved, or marked dynamic according to that choice. If a non-empty `[project.dependencies]` already exists in this situation, migration aborts with an explicit conflict instead of choosing one model and discarding the other.

[Multiple constraints dependencies](https://python-poetry.org/docs/main/dependency-specification/#multiple-constraints-poetry) are rendered directly from their structured Poetry dependency objects, in source order. No temporary dependency names or textual requirement rewrites are used.

When every dependency is safely representable, each non-Python legacy entry is removed after its complete PEP-508 representation has been generated. The separate Python constraint remains under Poetry when the selected strategy copies it rather than moving it. If Python is the only legacy dependency, the migration writes an explicit empty `[project.dependencies]` array: this declares that the authoritative standard runtime dependency model is intentionally empty while the Poetry Python constraint is retained for locking or dynamic metadata.

This cleanup is all-or-nothing for the non-Python main dependency model. If any main dependency needs Poetry-only state or fails semantic round-trip validation, no non-Python dependency or extra is partially migrated or cleaned up: those original `[tool.poetry.dependencies]` entries and the complete `[tool.poetry.extras]` declarations are retained, with `project.dependencies` marked as dynamic. Dependency groups use the same whole-group rule independently for each group.

You can **choose** whether to remove brackets around version specifiers in the generated PEP-508 strings:

- (*) remove them for PEP-508 compliance (e.g. `package>=1.0,<2.0`)
- or, keep them for compatibility with old generated output (e.g. `package (>=1.0,<2.0)`)

Per [PEP-508](https://peps.python.org/pep-0508/), brackets around version specifiers should not be generated, only accepted for compatibility with PEP-345.

Removing brackets is performed from parsed requirement fields rather than by editing the generated string. Constraint order, marker contents, and direct-reference formatting are otherwise preserved.

### Dependency Groups Migration

Poetry 2.2 added support for standard [PEP-735 dependency groups](https://packaging.python.org/en/latest/specifications/dependency-groups/). Poetry 2.2.1 fixed support for declaring such a group as optional, so this plugin requires at least 2.2.1. The plugin migrates representable dependencies from `[tool.poetry.group.<name>.dependencies]` and the legacy `[tool.poetry.dev-dependencies]` table into `[dependency-groups]`. If any dependency does not pass the PEP-508 round-trip check, the complete Poetry group is kept.

Poetry-specific group metadata remains in place. For example, an optional group is represented as:

```toml
[dependency-groups]
docs = ["mkdocs>=1.6,<2.0"]

[tool.poetry.group.docs]
optional = true
```

`include-groups` entries become PEP-735 `{ include-group = "..." }` entries. If a group contains a dependency that cannot be represented safely—such as a relative path or a private `source`—the entire group is kept in its original Poetry table and a warning is emitted.

### Example
This is an [example for testing](./tests/fixtures/poetry18/):

#### Before

```toml
# This file is part of the poetry-plugin-migrate project.

# Some comments on this line
[tool.poetry]
package-mode = false # Hey this should not be touched
name = "poetry-18"
version = "1.2.3"
description = "Test project that contains a pyproject.toml with Poetry v1.8 metadata."
license = "MIT"
authors = [
    "MaxMixAlex <MaxMixAlex@protonmail.com>",
    "Test Guy <test.guy@example.com>",
]
maintainers = [
    "Maintainer One <maintainer.one@example.com>",
    "Maintainer Two <maintainer.two@other.example.com>",
]
readme = ["README1.md", "README2.md"]
homepage = "https://example.com/"
repository = "https://github.com/zyf722/poetry-plugin-migrate"
documentation = "https://anyway.we.need.a.documentation.website/"
keywords = ["we", "just", "need", "some", "keywords", "for", "this", "project"]
classifiers = [
    "Development Status :: 4 - Beta",
    "Environment :: Console",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Topic :: Software Development",
    "Topic :: System",
    "Topic :: Terminals",
    "Typing :: Typed",
    "Operating System :: OS Independent",
]
packages = [{ include = "poetry18" }] # This should not be touched too

[tool.poetry.urls]
"Test custom URL" = "https://how.are.you/doing/"
"Just another one" = "https://another.one/"

[tool.poetry.scripts]
run_as_fast_as_possible = "poetry18.__main__:main"
poet = { reference = "write_some_poem.exe", type = "file" } # File-based scripts!

[tool.poetry.extras]
birthday-present = ["chocolate"]
networking = ["requests", "httpx"]

[tool.poetry.plugins."poetry.application.plugin"]
hi = "poetry18.plugins:ActuallyThereIsNoSuchPlugin"

[[tool.poetry.source]]
name = "private"
url = "http://a.source.too.secret/simple"
priority = "supplemental"

[tool.poetry.dependencies]
python = "^3.9"
careter = "^1.2.3"
tilder = "~1.2.3"
wildcarder = "1.*"
inequalitier = ">=1.2.3,<2.0.0"
exacter = "1.2.3"
equal-exacter = "==1.2.3"
git-branch = { git = "https://github.com/example/branch.git", branch = "next" }
git-rev = { git = "https://github.com/example/rev.git", rev = "deadbeef" }
git-tag = { git = "https://github.com/example/tag.git", tag = "1.2.3" }
git-subdir = { git = "https://github.com/example/subdir.git", subdirectory = "subdir" }
local-package = { path = "../local_package/", develop = true }
local-package-absolute = { path = "/path/to/absolute/package/", develop = true }
url = { url = "https://example.com/url-package-0.1.0.tar.gz" }
baby = { version = "^0.12.0", extras = ["toy-1", "toy-2"] }
spy = { version = "*", source = "private" }
tomli = { version = "^2.0.1", python = "<3.11" }
pathlib2 = { version = "^2.2", markers = "python_version <= '3.4' or sys_platform == 'win32'" }
foo = [
    { platform = "win32", version = "^2.0", python = ">=3.8", source = "private" },
    { platform = "darwin", url = "https://example.com/example-1.0-py3-none-any.whl" },
    { platform = "linux", version = "^1.0", python = ">=3.6,<3.8" },
]
chocolate = [
    { platform = "win32", version = "^1.0", optional = true, source = "private" },
    { platform = "darwin", version = "~2.0", optional = true },
    { platform = "linux", version = "==3.0", optional = true },
]
requests = { version = "^2.0", optional = true, python = "^3.6" }
httpx = { version = "^0.23", optional = true, python = "^3.6" }

[tool.poetry.dependencies.big-guy]
version = ">=18.0.0"
allow-prereleases = true
python = "^3.9"
markers = "platform_python_implementation == 'CPython'"

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

```

#### Expected behavior

This fixture sets `package-mode = false` but still contains complete legacy name and version metadata, so it remains a comprehensive end-to-end migration fixture and can produce a valid `[project]` table. Its complete asserted output is kept in the [expected fixture](./tests/fixtures/poetry18/non-interactive.expected.tpl.toml) rather than duplicated in this README. A non-package project without enough metadata to form a valid `[project]` skips only PEP 621 migration; independent dependency-group, Poetry requirement, build-system, and optional layout operations remain available.

## Contributing
This plugin still requires more testing and feedback to improve its quality and may contain bugs. Contributions in the form of [raising issues](https://github.com/zyf722/poetry-plugin-migrate/issues) and [code contributions](https://github.com/zyf722/poetry-plugin-migrate/pulls) are highly welcome.

It is strongly recommended to follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification when writing commit messages and creating pull requests.

## License
[MIT](./LICENSE)

