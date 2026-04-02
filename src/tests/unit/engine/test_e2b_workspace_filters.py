from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ii_agent.agents.sandboxes.e2b import E2BSandbox
from ii_agent.agents.sandboxes.schemas import SandboxStatus

pytestmark = pytest.mark.unit


@pytest.mark.asyncio
async def test_list_files_recursive_skips_ii_app_cache_dirs():
    manager = E2BSandbox(
        sandbox_id="sb-1",
        session_id="session-1",
        provider_sandbox_id="provider-1",
        status=SandboxStatus.RUNNING,
        sandbox=SimpleNamespace(),
        expired_at=datetime.now(timezone.utc),
    )
    manager._ensure_sandbox_connection = AsyncMock()
    manager.sandbox = SimpleNamespace(
        files=SimpleNamespace(
            list=AsyncMock(
                side_effect=[
                    [
                        SimpleNamespace(name=".ii_app", type="dir", mode=None, size=None),
                        SimpleNamespace(name=".ii-app", type="dir", mode=None, size=None),
                        SimpleNamespace(name="src", type="dir", mode=None, size=None),
                        SimpleNamespace(name="README.md", type="file", mode=None, size=32),
                    ],
                    [],
                ]
            )
        )
    )

    tree = await manager.list_files_recursive("/workspace")

    assert [child.name for child in tree.children] == ["src", "README.md"]
