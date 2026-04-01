"""Fresh-process import tests for billing package boundaries."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

pytestmark = pytest.mark.unit


def _project_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _run_python_import(code: str) -> subprocess.CompletedProcess[str]:
    project_root = _project_root()
    env = dict(os.environ)
    source_root = str(project_root / "src")
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = f"{source_root}{os.pathsep}{existing}" if existing else source_root
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=project_root,
        env=env,
        text=True,
        capture_output=True,
    )


def test_credit_service_imports_in_fresh_process() -> None:
    result = _run_python_import(
        "from ii_agent.credits.service import CreditService; "
        "print(CreditService.__name__)"
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_credit_repository_imports_in_fresh_process() -> None:
    result = _run_python_import(
        "from ii_agent.billing.credit_repository import CreditRepository; "
        "print(CreditRepository.__name__)"
    )
    assert result.returncode == 0, result.stderr or result.stdout
