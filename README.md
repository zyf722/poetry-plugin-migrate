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

### Backup

By default, the command runs `poetry check`, then applies the [migration rules](#migration-rules) using your interactive choices. Poetry checks the result before the plugin writes any file.

Backups are created only after migration and validation succeed. Existing backups are never overwritten: after `pyproject.bak.toml`, the command uses `pyproject.bak.1.toml`, `pyproject.bak.2.toml`, and so on.

If migration makes no changes, a normal run creates no backup and does not rewrite the file. `--dry-run` still prints the unchanged result.

### Optional table order

The final interactive prompt asks whether to reorder the top-level tables. This is disabled by default, including in `--no-interaction` mode.

As the Python packaging specifications for [project metadata](https://packaging.python.org/en/latest/specifications/pyproject-toml/) and [dependency groups](https://packaging.python.org/en/latest/specifications/dependency-groups/) do not recommend an order, the following is only this plugin's formatting convention:

1. `[project]`
2. `[dependency-groups]`
3. the `[tool]` namespace, with all `[tool.poetry]` and `[tool.poetry.*]` tables before other tool tables
4. other top-level tables, retaining their relative order
5. `[build-system]`

Only whole table sections are moved. Within `[tool]`, Poetry sections move before other tools, while the existing order inside both groups is kept.

The layout option does not reorder fields, group names, requirement arrays, nested tables, or tool-specific configuration.

### Comments and generated strings

[`tomlkit`](https://github.com/python-poetry/tomlkit) keeps comments and blank lines, but it cannot know which section a comment was intended to describe. Reordering therefore moves each whole table section together with the comments and blank lines attached to it. A comment between two sections may move with the section above it.

During migration, unambiguously associated dependency comments stay with their generated requirements. Comments without a clear destination are restored at the end of the document with a warning instead of being silently lost. Shared optional dependencies do not duplicate their source comment.

If `[tool.poetry]` is split across several places in the file, the plugin brings those parts together only when it needs to edit them. Newly generated values use TOML [single-quoted strings](https://toml.io/en/v1.0.0#literal-string) when possible and [double-quoted strings](https://toml.io/en/v1.0.0#basic-string) when needed. Existing values keep their original quoting, and `--no-literal` does not rewrite the whole document.

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
| `[tool.poetry.license]` | `[project.license]` | Moved only if it is already a valid [SPDX license expression](https://packaging.python.org/en/latest/specifications/pyproject-toml/#license); older free-form license text is left for manual migration |
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

If a field already exists in `[project]`, the plugin treats it as the value you chose. A matching simple value can be removed from `[tool.poetry]`. If the values disagree, or the older value is a list or table, the plugin leaves it in place and shows a warning instead of trying to combine the two. It changes [`project.dynamic`](https://packaging.python.org/en/latest/specifications/pyproject-toml/#dynamic) only when needed for a field being migrated; Poetry reports conflicts that were already present.

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

A license moves to `[project.license]` only when it is already a valid [SPDX license expression](https://packaging.python.org/en/latest/specifications/pyproject-toml/#license), such as `MIT`. Free-form text such as `MIT License` remains in `[tool.poetry.license]`; `"license"` is added to [`project.dynamic`](https://packaging.python.org/en/latest/specifications/pyproject-toml/#dynamic), and a warning asks you to review it manually rather than guessing the intended license.

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

Poetry accepts some Python version rules that [`project.requires-python`](https://packaging.python.org/en/latest/specifications/pyproject-toml/#requires-python) cannot express, including alternatives joined with `||` and some comparisons involving local version labels.

In these cases, the value remains under `[tool.poetry.dependencies.python]`; `requires-python` is added to [`project.dynamic`](https://packaging.python.org/en/latest/specifications/pyproject-toml/#dynamic), and the plugin shows a warning instead of writing an invalid value.

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

#### When dependencies cannot be moved safely

If `[project.dependencies]` or `[project.optional-dependencies]` already contains entries, the plugin keeps those entries and does not try to combine them with the Poetry sections. An empty list or table may be filled during migration. Migration also stops if two dependency or extra names refer to the same [normalized package name](https://packaging.python.org/en/latest/specifications/name-normalization/)—for example, `some-package` and `some_package`—rather than choosing one silently.

The plugin asks both [`packaging`](https://packaging.pypa.io/en/stable/requirements.html) and Poetry to read every generated requirement and checks that its meaning has not changed. Some Poetry dependency forms cannot be written completely as [PEP 508 requirements](https://peps.python.org/pep-0508/), including:

- relative paths;
- [Poetry-only settings](https://python-poetry.org/docs/main/dependency-specification/) such as `source`, `allow-prereleases`, and `develop`;
- version unions such as `>=1,<2 || >=3,<4`.

A URL that points directly to a [wheel file](https://packaging.python.org/en/latest/specifications/binary-distribution-format/) is handled as one limited exception: Poetry may read a version from the `.whl` filename even though the URL already selects that exact file.

The exception applies only to unconstrained URL dependencies ending in `.whl`. The URL, extras, markers, and all other direct-reference fields must still match.

If any main dependency other than the Python version cannot be moved safely, the plugin keeps all of `[tool.poetry.dependencies]` and `[tool.poetry.extras]`, then adds `"dependencies"` to [`project.dynamic`](https://packaging.python.org/en/latest/specifications/pyproject-toml/#dynamic).

This is all-or-nothing because `[project.dependencies]` determines which dependencies are recorded in the built package. Moving only the easy entries could leave a private-source or relative-path dependency out of the package by mistake.

Your choice for the Python version is handled separately. Dependencies that can be moved safely, including [multiple constraints](https://python-poetry.org/docs/main/dependency-specification/#multiple-constraints-poetry), keep their original order. Each dependency group is checked separately using the same all-or-nothing rule.

#### Requirement formatting

You can **choose** whether to remove brackets around version specifiers in the generated PEP-508 strings:

- (*) remove them for PEP-508 compliance (e.g. `package>=1.0,<2.0`)
- or, keep them for compatibility with old generated output (e.g. `package (>=1.0,<2.0)`)

Per [PEP-508](https://peps.python.org/pep-0508/), brackets around version specifiers should not be generated, only accepted for compatibility with PEP-345.

To remove brackets, the plugin rebuilds the requirement from its individual parts instead of using a text replacement. The order of version rules, environment markers, and direct URLs is otherwise kept.

### Dependency Groups Migration

Poetry 2.2 added support for standard [PEP-735 dependency groups](https://packaging.python.org/en/latest/specifications/dependency-groups/). Poetry 2.2.1 fixed optional group declarations, so this plugin requires at least 2.2.1.

The plugin moves dependencies that can be expressed as PEP 508 requirements from `[tool.poetry.group.<name>.dependencies]` and the older `[tool.poetry.dev-dependencies]` table into `[dependency-groups]`. If moving any dependency would change its meaning, the complete Poetry group is kept.

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
local-absolute-package = { path = "<% LOCAL_ABSOLUTE_PACKAGE %>", develop = true }
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

#### After (default non-interactive choices)

Running `poetry migrate --no-interaction` produces:

```toml
# This file is part of the poetry-plugin-migrate project.

# Some comments on this line
[tool.poetry]
package-mode = false # Hey this should not be touched
readme = ["README1.md", "README2.md"]
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

[tool.poetry.scripts]
poet = { reference = "write_some_poem.exe", type = "file" } # File-based scripts!

[tool.poetry.extras]
birthday-present = ["chocolate"]
networking = ["requests", "httpx"]

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
local-absolute-package = { path = "<% LOCAL_ABSOLUTE_PACKAGE %>", develop = true }
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

[project]
name = "poetry-18"
description = "Test project that contains a pyproject.toml with Poetry v1.8 metadata."
license = "MIT"
keywords = ["we", "just", "need", "some", "keywords", "for", "this", "project"]
version = "1.2.3"
dynamic = [
    "classifiers",
    "readme",
    "dependencies",
]
authors = [
    {name = "MaxMixAlex", email = "MaxMixAlex@protonmail.com"},
    {name = "Test Guy", email = "test.guy@example.com"},
]
maintainers = [
    {name = "Maintainer One", email = "maintainer.one@example.com"},
    {name = "Maintainer Two", email = "maintainer.two@other.example.com"},
]
requires-python = '>=3.9,<4.0'

[project.urls]
homepage = "https://example.com/"
repository = "https://github.com/zyf722/poetry-plugin-migrate"
documentation = "https://anyway.we.need.a.documentation.website/"
"Test custom URL" = "https://how.are.you/doing/"
"Just another one" = "https://another.one/"

[project.entry-points."poetry.application.plugin"]
hi = "poetry18.plugins:ActuallyThereIsNoSuchPlugin"


[project.scripts]
run_as_fast_as_possible = "poetry18.__main__:main"
```

Some dependencies in this example use Poetry-only settings, so the plugin keeps the complete Poetry dependency sections and lists `dependencies` in [`project.dynamic`](https://packaging.python.org/en/latest/specifications/pyproject-toml/#dynamic). See [When dependencies cannot be moved safely](#when-dependencies-cannot-be-moved-safely) for details.

A non-package project without enough information for `[project]` skips only the [PEP 621](https://peps.python.org/pep-0621/) migration. Dependency groups, Poetry requirements, build-system updates, and optional table ordering remain available.

## Contributing

This plugin still requires more testing and feedback to improve its quality and may contain bugs. Contributions in the form of [raising issues](https://github.com/zyf722/poetry-plugin-migrate/issues) and [code contributions](https://github.com/zyf722/poetry-plugin-migrate/pulls) are highly welcome.

It is strongly recommended to follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification when writing commit messages and creating pull requests.

## License

[MIT](./LICENSE)

