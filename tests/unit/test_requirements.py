from __future__ import annotations

from collections.abc import Mapping

import pytest
from packaging.requirements import Requirement
from poetry.core.factory import Factory
from poetry.core.packages.dependency import Dependency

from poetry_plugin_migrate.requirements import (
    UnrepresentableRequirementError,
    render_pep508_requirement,
)

DependencySpec = str | Mapping[str, object]


@pytest.mark.parametrize(
    ("constraint", "expected"),
    [
        ("*", "Dummy_Pkg"),
        ("1.2.3", "Dummy_Pkg==1.2.3"),
        ("1.2.*", "Dummy_Pkg==1.2.*"),
        ("^1.2", "Dummy_Pkg>=1.2,<2.0"),
        ("~1.2", "Dummy_Pkg>=1.2,<1.3"),
        (">=1,!=1.5.*,<2", "Dummy_Pkg>=1,!=1.5.*,<2"),
        (
            {"version": "^1.2", "extras": ["Zulu", "alpha"]},
            "Dummy_Pkg[alpha,zulu]>=1.2,<2.0",
        ),
        (
            {"version": ">=1", "markers": 'sys_platform in "linux (>=1)"'},
            'Dummy_Pkg>=1 ; sys_platform in "linux (>=1)"',
        ),
        (
            {"version": "^1.2", "python": ">=3.10,<3.13"},
            'Dummy_Pkg>=1.2,<2.0 ; python_version >= "3.10" and python_version < "3.13"',
        ),
    ],
)
def test_structured_renderer_only_removes_version_brackets(
    constraint: DependencySpec, expected: str
) -> None:
    dependency = Factory.create_dependency("Dummy_Pkg", constraint)
    raw = dependency.to_pep_508()

    rendered = render_pep508_requirement(dependency, keep_version_brackets=False)

    assert rendered == expected
    assert Requirement(rendered) == Requirement(raw)


def test_structured_renderer_can_keep_poetry_version_brackets() -> None:
    dependency = Factory.create_dependency(
        "dummy", {"version": ">=1,<2", "markers": 'sys_platform == "win32"'}
    )

    assert (
        render_pep508_requirement(dependency, keep_version_brackets=True)
        == 'dummy (>=1,<2) ; sys_platform == "win32"'
    )


@pytest.mark.parametrize(
    "constraint",
    [
        ">=1,<2 || >=3,<4",
        ">=1!2.0+local,<1!3",
    ],
)
def test_non_pep508_poetry_constraints_are_rejected(constraint: str) -> None:
    dependency = Factory.create_dependency("dummy", constraint)

    with pytest.raises(UnrepresentableRequirementError):
        render_pep508_requirement(dependency, keep_version_brackets=False)


@pytest.mark.parametrize(
    ("name", "constraint"),
    [
        (
            "dummy-pkg",
            {"url": "https://example.invalid/dummy_pkg-1.0.tar.gz?download=1"},
        ),
        (
            "dummy-pkg",
            {
                "url": "https://example.invalid/dummy_pkg-1.0.tar.gz",
                "extras": ["b", "a"],
                "markers": 'sys_platform == "linux"',
            },
        ),
        (
            "dummy",
            {
                "git": "https://example.invalid/dummy.git",
                "rev": "abc123",
                "subdirectory": "pkg",
            },
        ),
    ],
)
def test_direct_references_are_not_reformatted(
    name: str, constraint: DependencySpec
) -> None:
    dependency = Factory.create_dependency(name, constraint)
    raw = dependency.to_pep_508()

    assert render_pep508_requirement(dependency, keep_version_brackets=False) == raw


@pytest.mark.parametrize(
    "constraint",
    [
        {"url": "https://example.invalid/dummy_pkg-1.2.3-py3-none-any.whl"},
        {"url": "https://example.invalid/dummy_pkg-1.2.3-1-py3-none-any.whl"},
        {"url": "https://example.invalid/dummy_pkg-1.2.3rc1-py3-none-any.whl"},
        {"url": "https://example.invalid/dummy_pkg-1.2.3.post1-py3-none-any.whl"},
        {"url": "https://example.invalid/dummy_pkg-1!2.3-py3-none-any.whl"},
        {"url": "https://example.invalid/dummy_pkg-1.2.3+cpu-py3-none-any.whl"},
        {
            "url": (
                "https://example.invalid/files/"
                "dummy_pkg-1.2.3-py3-none-any.whl?download=1"
            )
        },
        {
            "url": "https://example.invalid/dummy_pkg-1.2.3-py3-none-any.whl",
            "extras": ["speed", "cli"],
            "markers": 'python_version >= "3.10"',
        },
    ],
)
def test_wheel_url_allows_only_poetry_inferred_version(
    constraint: DependencySpec,
) -> None:
    dependency = Factory.create_dependency("dummy-pkg", constraint)
    raw = dependency.to_pep_508()
    round_tripped = Dependency.create_from_pep_508(raw)

    assert dependency.constraint.is_any()
    assert not round_tripped.constraint.is_any()
    assert render_pep508_requirement(dependency, keep_version_brackets=False) == raw


def test_wheel_url_rejects_filename_with_different_package_name() -> None:
    dependency = Factory.create_dependency(
        "declared-name",
        {"url": "https://example.invalid/other_name-1.0-py3-none-any.whl"},
    )

    with pytest.raises(
        UnrepresentableRequirementError,
        match="changes dependency semantics",
    ):
        render_pep508_requirement(dependency, keep_version_brackets=False)


def test_wheel_url_rejects_fragment_dropped_by_poetry_round_trip() -> None:
    dependency = Factory.create_dependency(
        "dummy-pkg",
        {
            "url": (
                "https://example.invalid/dummy_pkg-1.0-py3-none-any.whl#sha256=abc123"
            )
        },
    )

    with pytest.raises(
        UnrepresentableRequirementError,
        match="changes dependency semantics",
    ):
        render_pep508_requirement(dependency, keep_version_brackets=False)
