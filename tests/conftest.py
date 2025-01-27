from __future__ import annotations

from pathlib import Path

import pytest
from cleo.testers.application_tester import ApplicationTester
from poetry.console.application import Application
from poetry.factory import Factory

FIXTURES_DIR = Path(__file__).parent / "fixtures"

PYPROJECT_TOML = "pyproject.toml"
PYPROJECT_TEMPLATE_SUFFIX = ".tpl.toml"
EXPECTED_TOML = "pyproject.expected.toml"
EXPECTED_TEMPLATE_SUFFIX = ".expected.tpl.toml"

# We need this because we want to test a local absolute path
# but there's no way to hardcode since it depends on the environment
# here we dynamically replace the placeholder with the actual path
TEMPLATE_ARGS = {
    "LOCAL_ABSOLUTE_PACKAGE": (FIXTURES_DIR / "local_absolute_package")
    .absolute()
    .as_posix()
}


def from_template(template: str) -> str:
    for key, value in TEMPLATE_ARGS.items():
        template = template.replace(f"<% {key} %>", value)
    return template


@pytest.fixture
def project(request: pytest.FixtureRequest):
    project_name: str = request.param
    project_path = FIXTURES_DIR / project_name

    pyproject_path = project_path / PYPROJECT_TOML
    pyproject_template_path = pyproject_path.with_suffix(PYPROJECT_TEMPLATE_SUFFIX)

    if not pyproject_path.exists():
        pyproject_path.write_text(from_template(pyproject_template_path.read_text()))

    yield project_path

    if pyproject_template_path.exists():
        pyproject_path.unlink()


@pytest.fixture
def pyproject_file(project: Path) -> Path:
    return project / PYPROJECT_TOML


@pytest.fixture
def expected_file(request: pytest.FixtureRequest, project: Path):
    expected_file_name: str = request.param

    expected_pyproject_path = project / EXPECTED_TOML
    expected_pyproject_template_path = project / (
        expected_file_name + EXPECTED_TEMPLATE_SUFFIX
    )

    if not expected_pyproject_path.exists():
        expected_pyproject_path.write_text(
            from_template(expected_pyproject_template_path.read_text())
        )

    yield expected_pyproject_path

    if expected_pyproject_template_path.exists():
        expected_pyproject_path.unlink()


@pytest.fixture
def application_tester(project: Path):
    app = Application()
    app._poetry = Factory().create_poetry(project)
    return ApplicationTester(app)
