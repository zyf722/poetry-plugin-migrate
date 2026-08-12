from __future__ import annotations

from collections.abc import Mapping

import pytest
from packaging.requirements import Requirement
from poetry.core.factory import Factory

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
    "constraint",
    [
        {"url": "https://example.invalid/dummy_pkg-1.0.tar.gz?download=1"},
        {
            "url": "https://example.invalid/dummy_pkg-1.0.tar.gz",
            "extras": ["b", "a"],
            "markers": 'sys_platform == "linux"',
        },
        {
            "git": "https://example.invalid/dummy.git",
            "rev": "abc123",
            "subdirectory": "pkg",
        },
    ],
)
def test_direct_references_are_not_reformatted(constraint: DependencySpec) -> None:
    dependency = Factory.create_dependency("dummy", constraint)
    raw = dependency.to_pep_508()

    assert render_pep508_requirement(dependency, keep_version_brackets=False) == raw
