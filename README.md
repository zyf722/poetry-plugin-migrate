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

By default, the command performs a `poetry check` before migration and then attempts to migrate the current `pyproject.toml` based on several [rules](#migration-rules) and the user's responses to interactive prompts. A backup file, `pyproject.bak.toml`, will be created before migration.

For better readability, TOML literal strings are used for string fields. If you prefer to use basic strings instead, you can use the `--no-literal` option.

> **Note**: Internally, this plugin uses [`tomlkit`](https://github.com/python-poetry/tomlkit), a *style-preserving* TOML library, to parse and modify the `pyproject.toml` file. Hence, the migrated result might NOT be pretty-formatted and might need reformatting.

### Available Options
- `-n` / `--no-interaction`: Skip interactive prompts and use default migration strategies. This is a global Poetry option.
- `--no-check`: Skip `poetry check` for `pyproject.toml`.
- `--check-strict`: Fail if check reports warnings.
- `--no-backup`: Do not create a backup of `pyproject.toml` before migration.
- `--dry-run`: Run the migration without modifying the `pyproject.toml`. Migration result will be printed to the console.
- `--no-literal`: Use basic strings instead of literal strings in `pyproject.toml`.

## Migration Rules

### Directly-Migrated Fields
Following fields will be directly migrated:

| Before | After | Notes |
| :---: | :---: | :---: |
| `[tool.poetry.name]` | `[project.name]` | - |
| `[tool.poetry.description]` | `[project.description]` | - |
| `[tool.poetry.license]` | `[project.license]` | - |
| `[tool.poetry.keywords]` | `[project.keywords]` | - |
| `[tool.poetry.urls]` | `[project.urls]` | Will be merged with other fields migrated into `[project.urls]` |
| `[tool.poetry.homepage]` | `[project.urls.homepage]` | - |
| `[tool.poetry.repository]` | `[project.urls.repository]` | - |
| `[tool.poetry.documentation]` | `[project.urls.documentation]` | - |
| `[tool.poetry.plugins]` | `[project.entry-points]` | - |
| `[tool.poetry.scripts]` | `[project.scripts]` | Only for those are **NOT** of type `file` <br> See python-poetry/poetry#9510 for details |
| `[tool.poetry.authors]` | `[project.authors]` | Format changed from `"name <email>"` to `{"name": name, "email": email}` |
| `[tool.poetry.maintainers]` | `[project.maintainers]` | Format changed from `"name <email>"` to `{"name": name, "email": email}` |
| `[tool.poetry.extras]` | `[project.optional-dependencies]` | See [Dependencies Migration](#dependencies-migration) for details |

### Conditional-Migrated Fields
Fields below either need the user to choose migration strategies for them, or are migrated only under specific conditions.

The option marked with `(*)` is the default choice.

#### `[tool.poetry.version]`
You can **choose** one of the following strategies for this field:

- (*) move it to `[project]`
- or, keep it in `[tool.poetry]`

If you want to set the version dynamically via `poetry build --local-version` or you are using a plugin which sets the version dynamically, you should use *dynamic versioning* that keeps it in `[tool.poetry]` and adds `"version"` to `[project.dynamic]`.

Otherwise, this field will be moved to `[project]`.

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

Some dependency semantics cannot be represented completely in PEP-508 project metadata. These include relative paths, Poetry-only fields such as `source`, `allow-prereleases`, or `develop`, and version unions such as `>=1,<2 || >=3,<4`. Every generated requirement is parsed by both `packaging` and Poetry and must round-trip without changing its constraint, extras, markers, or direct-reference source. If any main dependency fails this check, the plugin keeps the complete `[tool.poetry.dependencies]` and `[tool.poetry.extras]` model together and adds `"dependencies"` to `[project.dynamic]`. It does not partially migrate the remaining dependencies, because Poetry does not merge every legacy-only field back into standardized dependencies. If `[project.dependencies]` already exists in this situation, migration aborts with an explicit conflict instead of choosing one model and discarding the other.

[Multiple constraints dependencies](https://python-poetry.org/docs/main/dependency-specification/#multiple-constraints-poetry) will be expanded into separate entries with temporary names before migration, which will then be merged into a single entry after all entries are migrated.

Fields that can be presented in a PEP-508 string (`version`, `git`, `branch`, `tag`, `rev`, `file`, `path`, `url`, `subdirectory`,) will be removed from the original entry.

Marker fields (`python`, `platform`, `markers`, `extras`) will only be removed if the constraint is NOT an expanded one from a multiple constraints dependency.

Then, original entries with no fields left will be removed. Others (e.g. `{source = "private"}`) will be kept for locking.

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

#### After (follows default migration strategies)

The fixture contains dependency semantics that are not completely representable in PEP 508, so the default result deliberately keeps its complete Poetry dependency model and marks `project.dependencies` as dynamic. The exact, tested output is maintained in [`non-interactive.expected.tpl.toml`](./tests/fixtures/poetry18/non-interactive.expected.tpl.toml) rather than duplicated here.

## Contributing
This plugin still requires more testing and feedback to improve its quality and may contain bugs. Contributions in the form of [raising issues](https://github.com/zyf722/poetry-plugin-migrate/issues) and [code contributions](https://github.com/zyf722/poetry-plugin-migrate/pulls) are highly welcome.

It is strongly recommended to follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification when writing commit messages and creating pull requests.

## License
[MIT](./LICENSE)

