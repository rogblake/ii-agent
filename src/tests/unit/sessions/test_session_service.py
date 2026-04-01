from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ii_agent.sessions.service import SessionService


class FakeEventRepo:
    async def get_by_session_filtered(self, db, session_id, excluded_types):
        return [
            SimpleNamespace(
                id="e1",
                session_id=session_id,
                created_at=datetime.now(timezone.utc),
                event_type="agent.tool.result",
                content={
                    "result": {
                        "type": "file_url",
                        "file_storage_path": "users/u1/file.txt",
                        "url": "old",
                    }
                },
                run_id=None,
            ),
            SimpleNamespace(
                id="e2",
                session_id=session_id,
                created_at=datetime.now(timezone.utc),
                event_type="system.notification",
                content={"message": "ignored"},
                run_id=None,
            ),
        ]


@pytest.mark.asyncio
async def test_get_session_events_enriches_file_url_and_filters_ignored(settings_factory):
    service = SessionService(
        session_repo=SimpleNamespace(),
        event_repo=FakeEventRepo(),
        run_task_service=SimpleNamespace(),
        file_store=SimpleNamespace(get_download_signed_url=lambda path: f"signed://{path}"),
        sandbox_repo=SimpleNamespace(),
        config=settings_factory(),
    )

    events = await service.get_session_events_with_details(None, "session-1")

    assert len(events) == 2
    tool_event = next(e for e in events if e["type"] == "agent.tool.result")
    assert tool_event["content"]["result"]["url"] == "signed://users/u1/file.txt"
