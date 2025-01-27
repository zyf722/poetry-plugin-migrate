from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

    from cleo.testers.application_tester import ApplicationTester


@pytest.mark.parametrize("project", ["poetry18"], indirect=True)
def test_poetry_loads_plugin(application_tester: ApplicationTester):
    """Poetry should work with the plugin for test projects."""
    application_tester.execute("migrate -h")
    assert application_tester.status_code == 0
    assert "migrate" in application_tester.io.fetch_output()


@pytest.mark.parametrize("project", ["poetry18"], indirect=True)
@pytest.mark.parametrize("expected_file", ["non-interactive"], indirect=True)
def test_non_interactive(
    application_tester: ApplicationTester, pyproject_file: Path, expected_file: Path
):
    application_tester.execute("migrate -n --no-backup")
    assert application_tester.status_code == 0
    assert pyproject_file.read_text() == expected_file.read_text()
