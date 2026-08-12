# CHANGELOG


## v0.2.0 (2026-08-12)

### Bug Fixes

- **command**: Preserve exact migration backups
  ([`5f29c9a`](https://github.com/zyf722/poetry-plugin-migrate/commit/5f29c9a759d7122c4a0d79c03ebdafabf4292c7e))

### Build System

- **deps**: Resolve Dependabot alerts
  ([`0b425f7`](https://github.com/zyf722/poetry-plugin-migrate/commit/0b425f777a059521aafb779034627379728a300c))

- **deps**: Update rapidfuzz for Python 3.14
  ([`f34749d`](https://github.com/zyf722/poetry-plugin-migrate/commit/f34749ddb89d8680a85ed96b9fac16191fd7868a))

- **poe**: Add static check task
  ([`dcc10e2`](https://github.com/zyf722/poetry-plugin-migrate/commit/dcc10e2b0723870f0e208835ef8cbd1de087ca89))

- **poetry**: Update Python and Poetry support
  ([#8](https://github.com/zyf722/poetry-plugin-migrate/pull/8),
  [`71e4da4`](https://github.com/zyf722/poetry-plugin-migrate/commit/71e4da4acd99088c39c1d9ca2a4f238353d7caae))

### Chores

- **license**: Update copyright year
  ([`b779e72`](https://github.com/zyf722/poetry-plugin-migrate/commit/b779e72b98517696f44673e16a99111849b3912b))

### Continuous Integration

- **release**: Release through protected main
  ([`d67e956`](https://github.com/zyf722/poetry-plugin-migrate/commit/d67e9569c6994093f618c72960777953382bf582))

- **release**: Secure trusted publishing
  ([`3e2285f`](https://github.com/zyf722/poetry-plugin-migrate/commit/3e2285fae8786e904c269960233eae77c4f6d2c8))

- **test**: Expand compatibility matrix
  ([#8](https://github.com/zyf722/poetry-plugin-migrate/pull/8),
  [`89fe6c3`](https://github.com/zyf722/poetry-plugin-migrate/commit/89fe6c34d797a139252b02984b9cbf415a96e2bd))

- **test**: Reuse matrix environment for checks
  ([`d618f12`](https://github.com/zyf722/poetry-plugin-migrate/commit/d618f1217319aa347777b533da279ec1e6fd6759))

### Documentation

- **readme**: Document migration workflow
  ([#4](https://github.com/zyf722/poetry-plugin-migrate/pull/4),
  [`4f58433`](https://github.com/zyf722/poetry-plugin-migrate/commit/4f584333e4dc3ab29a23c3cb4d4c70a1794ebd25))

### Features

- **migrator**: Harden project migration (#1, #2, #3, #5, #6, #7)
  ([`e47a875`](https://github.com/zyf722/poetry-plugin-migrate/commit/e47a875dba56246cc97317c6dc17cbc3c894f184))

### Testing

- **migration**: Cover safety regressions (#1, #5, #7)
  ([`0ec69e3`](https://github.com/zyf722/poetry-plugin-migrate/commit/0ec69e37dcbf8ba27398f18e9a1ff98cd51d4ff7))


## v0.1.1 (2025-01-27)

### Bug Fixes

- Fix missing space
  ([`2399e5b`](https://github.com/zyf722/poetry-plugin-migrate/commit/2399e5b8a1f09b910ac9f9c55ea9bc58853fc532))

### Testing

- Fix test case for simple project
  ([`f0ea4c7`](https://github.com/zyf722/poetry-plugin-migrate/commit/f0ea4c78c4061cb48571eb354a1269745bd6021f))


## v0.1.0 (2025-01-27)

### Bug Fixes

- Do not create corresponding target field if source field does not exist in `tool.poetry`
  ([`1841ed6`](https://github.com/zyf722/poetry-plugin-migrate/commit/1841ed6c677ff268d3883379fc82861cde90f972))

- **ci**: Fix mypy argument
  ([`f8cbcba`](https://github.com/zyf722/poetry-plugin-migrate/commit/f8cbcbaa2480a7f779cc6c529383c985e0c5cd62))

- **ci**: Remove isort
  ([`31ab127`](https://github.com/zyf722/poetry-plugin-migrate/commit/31ab127e002def966338510b5c479a99849e7a95))

- **test**: Fix tests
  ([`993d980`](https://github.com/zyf722/poetry-plugin-migrate/commit/993d980aad5dcf1ecf05f209a0973df2409c1eed))

### Chores

- Add .gitignore
  ([`65df1ff`](https://github.com/zyf722/poetry-plugin-migrate/commit/65df1ff0fa36b20c942bc8872ba939a9c25bc17d))

- Add LICENSE
  ([`418a375`](https://github.com/zyf722/poetry-plugin-migrate/commit/418a375ced01a01c2e9e1b5942650b42a9c73d34))

- Add README
  ([`af733e0`](https://github.com/zyf722/poetry-plugin-migrate/commit/af733e0332f10c3dcb363ad1494f9e07b57af084))

- Update .gitignore
  ([`bb13bdd`](https://github.com/zyf722/poetry-plugin-migrate/commit/bb13bddd528d37b42651d071523c4a069909d668))

- **release**: Prepare for release
  ([`4c512f0`](https://github.com/zyf722/poetry-plugin-migrate/commit/4c512f00e0541d92eda50bcbde37647cacb14107))

### Continuous Integration

- Add ci build
  ([`86ccbf8`](https://github.com/zyf722/poetry-plugin-migrate/commit/86ccbf82fe7ece5bb820e7a3ab4a8bdb592629a6))

- Remove unused release-please
  ([`de52c7b`](https://github.com/zyf722/poetry-plugin-migrate/commit/de52c7bc4e56d8c8f1b0e65dd0647c8813eab68b))

- Use latest python for checking
  ([`5b850b4`](https://github.com/zyf722/poetry-plugin-migrate/commit/5b850b4f6866afdf6fcfff653892008370617953))

### Features

- Initial commit
  ([`babdbb9`](https://github.com/zyf722/poetry-plugin-migrate/commit/babdbb9b968cab1a006ef6c5b233917c6b0e277b))

### Testing

- Add simple project for testing
  ([`708b183`](https://github.com/zyf722/poetry-plugin-migrate/commit/708b183ec5b387adf6c019a0e2a08e8587a4ea4f))

- Add test
  ([`d693b2b`](https://github.com/zyf722/poetry-plugin-migrate/commit/d693b2b82576705bdeefdf95e3fb400c563e22ba))
