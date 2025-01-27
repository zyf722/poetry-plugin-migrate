# Poetry Plugin: Migrate

[![License](https://img.shields.io/github/license/zyf722/poetry-plugin-migrate)](LICENSE)
[![PyPI version](https://img.shields.io/pypi/v/poetry-plugin-migrate?logo=pypi&logoColor=white&label=PyPI)](https://pypi.org/project/poetry-plugin-migrate/)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/poetry-plugin-migrate?logo=python&logoColor=white&label=Python)](https://pypi.org/project/poetry-plugin-migrate/)
[![Poetry version](https://img.shields.io/badge/Poetry-%3E%3D2.0-blue?logo=poetry&logoColor=white)](https://python-poetry.org/)
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

The plugin provides an `migrate` command to migrate current `pyproject.toml` to the new format:

```bash
poetry migrate
```

By default, the command performs a `poetry check` before migration and then attempts to migrate the current `pyproject.toml` based on several [rules](#migration-rules) and the user's responses to interactive prompts. A backup file, `pyproject.bak.toml`, will be created before migration.

For better readability, TOML literal strings are used for string fields. If you prefer to use basic strings instead, you can use the `--no-literal` option.

> **Note**: Internally, this plugin uses [`tomlkit`](https://github.com/python-poetry/tomlkit), a *style-preserving* TOML library, to parse and modify the `pyproject.toml` file. Hence, the migrated result might NOT be pretty-formatted and might need reformatting.

### Available Options
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

- (*) keep it in `[tool.poetry]`
- or, move it to `[project]`

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

- `>=2.0`
- `>=2.0,<3.0`
- `>=2.0.0`
- `>=2.0.0,<3.0.0`
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

[Multiple constraints dependencies](https://python-poetry.org/docs/main/dependency-specification/#multiple-constraints-poetry) will be expanded into separate entries with temporary names before migration, which will then be merged into a single entry after all entries are migrated.

Fields that can be presented in a PEP-508 string (`version`, `git`, `branch`, `tag`, `rev`, `file`, `path`, `url`, `subdirectory`,) will be removed from the original entry.

Marker fields (`python`, `platform`, `markers`, `extras`) will only be removed if the constraint is NOT an expanded one from a multiple constraints dependency.

Then, original entries with no fields left will be removed. Others (e.g. `{source = "private"}`) will be kept for locking.

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

```toml
# This file is part of the poetry-plugin-migrate project.

# Some comments on this line
[tool.poetry]
package-mode = false # Hey this should not be touched
version = "1.2.3"
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

[[tool.poetry.source]]
name = "private"
url = "http://a.source.too.secret/simple"
priority = "supplemental"

[tool.poetry.dependencies]
python = "^3.9"
local-package = { path = "../local_package/", develop = true }
local-package-absolute = {  develop = true }
spy = {  source = "private" }
foo = [{ platform = "win32",  python = ">=3.8", source = "private" }, { platform = "darwin"  }, { platform = "linux",  python = ">=3.6,<3.8" }]
chocolate = [{ platform = "win32",   source = "private" }, { platform = "darwin"   }, { platform = "linux"   }]

[tool.poetry.dependencies.big-guy]
allow-prereleases = true

[build-system]
requires = ["poetry-core"]
build-backend = "poetry.core.masonry.api"

[project]
name = "poetry-18"
description = "Test project that contains a pyproject.toml with Poetry v1.8 metadata."
license = "MIT"
keywords = ["we", "just", "need", "some", "keywords", "for", "this", "project"]
dynamic = ["version", "classifiers", "readme"]
authors = [{name = "Test Guy", email = "test.guy@example.com"}, {name = "MaxMixAlex", email = "MaxMixAlex@protonmail.com"}]
maintainers = [{name = "Maintainer Two", email = "maintainer.two@other.example.com"}, {name = "Maintainer One", email = "maintainer.one@example.com"}]
requires-python = '>=3.9,<4.0'
dependencies = ['careter (>=1.2.3,<2.0.0)', 'tilder (>=1.2.3,<1.3.0)', 'wildcarder (==1.*)', 'inequalitier (>=1.2.3,<2.0.0)', 'exacter (==1.2.3)', 'equal-exacter (==1.2.3)', 'git-branch @ git+https://github.com/example/branch.git@next', 'git-rev @ git+https://github.com/example/rev.git@deadbeef', 'git-tag @ git+https://github.com/example/tag.git@1.2.3', 'git-subdir @ git+https://github.com/example/subdir.git#subdirectory=subdir', 'local-package-absolute @ file:///<% LOCAL_ABSOLUTE_PACKAGE %>', 'url @ https://example.com/url-package-0.1.0.tar.gz', 'baby[toy-1,toy-2] (>=0.12.0,<0.13.0)', 'spy', 'tomli (>=2.0.1,<3.0.0) ; python_version < "3.11"', 'pathlib2 (>=2.2,<3.0) ; python_version <= "3.4" or sys_platform == "win32"', 'big-guy (>=18.0.0) ; python_version >= "3.9" and python_version < "4.0" and platform_python_implementation == "CPython"', 'foo (>=2.0,<3.0) ; python_version >= "3.8" and sys_platform == "win32"', 'foo @ https://example.com/example-1.0-py3-none-any.whl ; sys_platform == "darwin"', 'foo (>=1.0,<2.0) ; python_version >= "3.6" and python_version < "3.8" and sys_platform == "linux"']

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

[project.optional-dependencies]
birthday-present = ['chocolate (==3.0) ; sys_platform == "linux"','chocolate (>=2.0,<2.1) ; sys_platform == "darwin"','chocolate (>=1.0,<2.0) ; sys_platform == "win32"']
networking = ['requests (>=2.0,<3.0) ; python_version >= "3.6" and python_version < "4.0"', 'httpx (>=0.23,<0.24) ; python_version >= "3.6" and python_version < "4.0"']

```

## Contributing
This plugin still requires more testing and feedback to improve its quality and may contain bugs. Contributions in the form of [raising issues](https://github.com/zyf722/poetry-plugin-migrate/issues) and [code contributions](https://github.com/zyf722/poetry-plugin-migrate/pulls) are highly welcome.

It is strongly recommended to follow the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification when writing commit messages and creating pull requests.

## License
[MIT](./LICENSE)

