from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
import uuid

import pytest
from sqlalchemy.dialects import postgresql

from ii_agent.credits.repository import CreditTransactionRepository


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one(self):
        return self._value


class _RowsResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _RecordingSession:
    def __init__(self, rows):
        self.statements = []
        self._responses = [_ScalarResult(1), _RowsResult(rows)]

    async def execute(self, statement):
        self.statements.append(statement)
        return self._responses.pop(0)


@pytest.mark.asyncio
async def test_get_session_summaries_casts_session_id_when_session_name_missing() -> None:
    repo = CreditTransactionRepository()
    session_id = uuid.uuid4()
    updated_at = datetime.now(timezone.utc)
    db = _RecordingSession(
        [
            SimpleNamespace(
                session_id=session_id,
                session_title=str(session_id),
                credits=Decimal("-1.250000"),
                bonus_credits=Decimal("0"),
                updated_at=updated_at,
            )
        ]
    )

    sessions, total = await repo.get_session_summaries(
        db=db,
        user_id=uuid.uuid4(),
        page=1,
        per_page=20,
    )

    compiled = str(
        db.statements[1].compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "CAST(credit_transactions.session_id AS VARCHAR)" in compiled
    assert sessions == [
        {
            "session_id": str(session_id),
            "session_title": str(session_id),
            "credits": 1.25,
            "bonus_credits": 0.0,
            "updated_at": updated_at,
        }
    ]
    assert total == 1
