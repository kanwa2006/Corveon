"""Foundation smoke test.

Verifies the backend package scaffold imports cleanly. This keeps the CI test
gate meaningful (and non-empty) before feature code lands; real per-layer tests
are added with each feature per docs/DEVELOPER.md.
"""

import importlib

import pytest

_PACKAGES = [
    "app",
    "app.api",
    "app.orchestrator",
    "app.agents",
    "app.providers",
    "app.evidence",
    "app.medication",
    "app.ingestion",
    "app.data",
    "app.core",
    "app.workers",
]


@pytest.mark.unit
@pytest.mark.parametrize("name", _PACKAGES)
def test_package_imports(name: str) -> None:
    assert importlib.import_module(name) is not None
