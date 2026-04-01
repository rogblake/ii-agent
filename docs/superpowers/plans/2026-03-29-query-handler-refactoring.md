# Query Handler Refactoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract domain logic from `realtime/handlers/query.py` into proper domain services (plans, files/media) following DDD and SOLID, with TDD.

**Architecture:** Create a new `plans/` domain for milestone lifecycle. Move `agents/media/` to `files/media/` so media types are available project-wide. Update `FileService.prepare_agent_files()` to return typed media objects. Refactor both `query.py` and `plan.py` handlers to delegate to domain services.

**Tech Stack:** Python 3.11+, Pydantic v2, SQLAlchemy 2.0 async, pytest

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `src/ii_agent/plans/__init__.py` | Public exports for plans domain |
| `src/ii_agent/plans/types.py` | `MilestoneStatus` StrEnum |
| `src/ii_agent/plans/schemas.py` | Pydantic models for plan/milestone data |
| `src/ii_agent/plans/service.py` | `PlanService` — milestone context + status lifecycle |
| `src/ii_agent/plans/exceptions.py` | Domain exceptions |
| `src/ii_agent/files/media/__init__.py` | Re-exports Image, File, Video, Audio |
| `src/ii_agent/files/media/media.py` | Moved from `agents/media/media.py` |
| `src/tests/unit/plans/__init__.py` | Test package |
| `src/tests/unit/plans/test_plan_service.py` | Unit tests for PlanService |
| `src/tests/unit/files/test_prepare_agent_files_typed.py` | Tests for typed prepare_agent_files |

### Modified Files

| File | Change |
|------|--------|
| `src/ii_agent/files/__init__.py` | Add media type re-exports |
| `src/ii_agent/files/service.py` | Update `prepare_agent_files()` return type to use Image/File |
| `src/ii_agent/core/container.py` | Wire `PlanService` |
| `src/ii_agent/realtime/handlers/query.py` | Remove domain logic, delegate to services |
| `src/ii_agent/realtime/handlers/plan.py` | Update imports, use FileService for file uploads |
| 19 source files under `src/ii_agent/agents/` | Update `from ii_agent.agents.media` → `from ii_agent.files.media` |
| ~30 test files under `src/tests/unit/engine/` | Update media imports |

### Deleted Files

| File | Reason |
|------|--------|
| `src/ii_agent/agents/media/__init__.py` | Moved to `files/media/` |
| `src/ii_agent/agents/media/media.py` | Moved to `files/media/` |

---

### Task 1: Move `agents/media/` to `files/media/`

**Files:**
- Create: `src/ii_agent/files/media/__init__.py`
- Create: `src/ii_agent/files/media/media.py`
- Modify: `src/ii_agent/files/__init__.py`
- Delete: `src/ii_agent/agents/media/__init__.py`
- Delete: `src/ii_agent/agents/media/media.py`
- Test: `src/tests/unit/engine/test_v1_media_types.py` (existing, update import)

- [ ] **Step 1: Copy media.py to new location**

Copy `src/ii_agent/agents/media/media.py` to `src/ii_agent/files/media/media.py` (no changes to content).

- [ ] **Step 2: Create `files/media/__init__.py`**

```python
from ii_agent.files.media.media import Audio, File, Image, Video

__all__ = ["Audio", "File", "Image", "Video"]
```

- [ ] **Step 3: Update `files/__init__.py` to re-export media types**

Add to `src/ii_agent/files/__init__.py`:

```python
# After existing imports, add:
from ii_agent.files.media import Audio, File, Image, Video

# Add to __all__:
    # Media types
    "Audio",
    "File",
    "Image",
    "Video",
```

- [ ] **Step 4: Delete old `agents/media/` directory**

Remove:
- `src/ii_agent/agents/media/media.py`
- `src/ii_agent/agents/media/__init__.py`

- [ ] **Step 5: Run existing media type tests to verify move**

```bash
pytest src/tests/unit/engine/test_v1_media_types.py -v
```

Expected: FAIL (old import path no longer exists)

- [ ] **Step 6: Update test import and verify**

In `src/tests/unit/engine/test_v1_media_types.py`, change:
```python
# OLD
from ii_agent.agents.media.media import Audio, File, Image, Video
# NEW
from ii_agent.files.media import Audio, File, Image, Video
```

```bash
pytest src/tests/unit/engine/test_v1_media_types.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/ii_agent/files/media/ src/ii_agent/files/__init__.py src/tests/unit/engine/test_v1_media_types.py
git add -u src/ii_agent/agents/media/
git commit -m "refactor: move agents/media/ to files/media/ domain"
```

---

### Task 2: Update all source imports from `agents.media` to `files.media`

**Files:**
- Modify: 19 source files under `src/ii_agent/agents/` and `src/ii_agent/realtime/handlers/`

The following files need import updates. Each uses one of these patterns:

**Pattern A** — `from ii_agent.agents.media import X` → `from ii_agent.files.media import X`

Files:
- `src/ii_agent/agents/agent.py`
- `src/ii_agent/agents/models/base.py`
- `src/ii_agent/agents/models/message.py`
- `src/ii_agent/agents/models/response.py`
- `src/ii_agent/agents/models/google/gemini.py`
- `src/ii_agent/agents/models/google/interactions.py`
- `src/ii_agent/agents/runs/agent.py`
- `src/ii_agent/agents/runs/base.py`
- `src/ii_agent/agents/runs/events.py`
- `src/ii_agent/agents/tools/function.py`
- `src/ii_agent/agents/utils/agent.py`
- `src/ii_agent/agents/utils/media.py`
- `src/ii_agent/agents/utils/openai.py`
- `src/ii_agent/agents/sandboxes/media_uploader.py`
- `src/ii_agent/realtime/handlers/query.py`
- `src/ii_agent/realtime/handlers/plan.py`

**Pattern B** — `from ii_agent.agents.media.media import X` → `from ii_agent.files.media import X`

Files:
- `src/ii_agent/agents/models/openai/completions.py`
- `src/ii_agent/agents/models/openai/responses.py`
- `src/ii_agent/agents/models/anthropic/claude.py`

- [ ] **Step 1: Update all Pattern A imports**

For each of the 16 files listed under Pattern A, replace:
```python
from ii_agent.agents.media import ...
```
with:
```python
from ii_agent.files.media import ...
```

- [ ] **Step 2: Update all Pattern B imports**

For each of the 3 files listed under Pattern B, replace:
```python
from ii_agent.agents.media.media import ...
```
with:
```python
from ii_agent.files.media import ...
```

- [ ] **Step 3: Verify all source imports resolve**

```bash
python -c "from ii_agent.agents.agent import IIAgent; print('OK')"
python -c "from ii_agent.realtime.handlers.query import UserQueryHandler; print('OK')"
python -c "from ii_agent.realtime.handlers.plan import PlanHandler; print('OK')"
```

Expected: All print `OK`

- [ ] **Step 4: Commit**

```bash
git add -u src/ii_agent/
git commit -m "refactor: update all source imports from agents.media to files.media"
```

---

### Task 3: Update all test imports from `agents.media` to `files.media`

**Files:**
- Modify: ~30 test files under `src/tests/unit/engine/`

Test files that need updating (all use `from ii_agent.agents.media` or `from ii_agent.agents.media.media`):

- `src/tests/unit/engine/test_v1_models_gemini_deep.py`
- `src/tests/unit/engine/test_v1_utils_agent.py`
- `src/tests/unit/engine/test_v1_message_model_deep.py`
- `src/tests/unit/engine/test_v1_agents_agent_deep.py` (multiple local imports)
- `src/tests/unit/engine/test_v1_models_claude_deep.py`
- `src/tests/unit/engine/test_v1_run_agent_deep.py` (many local imports)
- `src/tests/unit/engine/test_v1_agent_main_r4.py`
- `src/tests/unit/engine/test_v1_models_google_gemini.py`
- `src/tests/unit/engine/test_v1_models_openai_deep.py`
- `src/tests/unit/engine/test_v1_models_openai_completions.py`
- `src/tests/unit/engine/test_v1_sessions_media_r4.py`
- `src/tests/unit/engine/test_v1_models_google_interactions.py`
- `src/tests/unit/engine/test_v1_tools_function_deep.py`
- `src/tests/unit/engine/test_sandbox_media_uploader.py`

- [ ] **Step 1: Update all top-level test imports**

Replace all occurrences of:
```python
from ii_agent.agents.media import ...
from ii_agent.agents.media.media import ...
```
with:
```python
from ii_agent.files.media import ...
```

For local imports inside test functions (e.g., in `test_v1_agents_agent_deep.py`, `test_v1_run_agent_deep.py`, `test_v1_sessions_media_r4.py`), apply the same replacement.

- [ ] **Step 2: Run media-related tests**

```bash
pytest src/tests/unit/engine/test_v1_media_types.py src/tests/unit/engine/test_sandbox_media_uploader.py -v
```

Expected: PASS

- [ ] **Step 3: Run broader test suite to verify no broken imports**

```bash
pytest src/tests/unit/engine/ -v --co -q 2>&1 | tail -5
```

Expected: All tests collected without import errors

- [ ] **Step 4: Commit**

```bash
git add -u src/tests/
git commit -m "refactor: update all test imports from agents.media to files.media"
```

---

### Task 4: Update `FileService.prepare_agent_files()` to return typed media objects

**Files:**
- Modify: `src/ii_agent/files/service.py`
- Test: `src/tests/unit/files/test_prepare_agent_files_typed.py`

- [ ] **Step 1: Write failing test for typed return**

Create `src/tests/unit/files/test_prepare_agent_files_typed.py`:

```python
"""Tests for FileService.prepare_agent_files() returning typed media objects."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from ii_agent.files.media import File, Image
from ii_agent.files.schemas import FileDataResponse
from ii_agent.files.service import FileService


def _make_file_service() -> FileService:
    return FileService(
        file_repo=MagicMock(),
        session_repo=MagicMock(),
        storage=AsyncMock(),
        config=MagicMock(),
    )


def _file_response(
    *,
    file_id: uuid.UUID | None = None,
    name: str = "test.txt",
    url: str = "https://example.com/test.txt",
    content_type: str = "text/plain",
) -> FileDataResponse:
    return FileDataResponse(
        id=file_id or uuid.uuid4(),
        name=name,
        url=url,
        content_type=content_type,
        size=100,
        storage_path="path/to/file",
        upload_status="complete",
        is_public=False,
        created_at=None,
        asset_type="document",
        source="user_upload",
    )


@pytest.mark.asyncio
async def test_prepare_agent_files_returns_typed_image_and_file() -> None:
    """prepare_agent_files should return (list[Image], list[File])."""
    svc = _make_file_service()
    img_id = uuid.uuid4()
    file_id = uuid.uuid4()

    svc.get_files_by_ids_and_update_session = AsyncMock(
        return_value=[
            _file_response(file_id=img_id, name="photo.png", url="https://cdn/photo.png", content_type="image/png"),
            _file_response(file_id=file_id, name="doc.pdf", url="https://cdn/doc.pdf", content_type="application/pdf"),
        ]
    )

    db = AsyncMock()
    images, files = await svc.prepare_agent_files(
        db,
        file_ids=[img_id, file_id],
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )

    assert len(files) == 2
    assert all(isinstance(f, File) for f in files)
    assert files[0].url == "https://cdn/photo.png"
    assert files[0].filename == "photo.png"

    assert len(images) == 1
    assert all(isinstance(i, Image) for i in images)
    assert images[0].url == "https://cdn/photo.png"
    assert images[0].mime_type == "image/png"


@pytest.mark.asyncio
async def test_prepare_agent_files_skips_files_without_url() -> None:
    svc = _make_file_service()
    svc.get_files_by_ids_and_update_session = AsyncMock(
        return_value=[
            _file_response(name="no-url.txt", url=None),
        ]
    )

    db = AsyncMock()
    images, files = await svc.prepare_agent_files(
        db,
        file_ids=[uuid.uuid4()],
        user_id=uuid.uuid4(),
        session_id=uuid.uuid4(),
    )

    assert images == []
    assert files == []


@pytest.mark.asyncio
async def test_prepare_agent_files_empty_file_ids() -> None:
    svc = _make_file_service()
    svc.get_files_by_ids_and_update_session = AsyncMock(return_value=[])

    db = AsyncMock()
    images, files = await svc.prepare_agent_files(
        db, file_ids=[], user_id=uuid.uuid4(), session_id=uuid.uuid4(),
    )

    assert images == []
    assert files == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest src/tests/unit/files/test_prepare_agent_files_typed.py -v
```

Expected: FAIL — `prepare_agent_files` returns `tuple[list[dict], list[dict]]` not `tuple[list[Image], list[File]]`

- [ ] **Step 3: Update `FileService.prepare_agent_files()` implementation**

In `src/ii_agent/files/service.py`, update the method:

```python
    async def prepare_agent_files(
        self,
        db: AsyncSession,
        *,
        file_ids: list[uuid.UUID],
        user_id: uuid.UUID,
        session_id: uuid.UUID,
    ) -> tuple[list[Image], list[File]]:
        """Fetch files by IDs and separate into images and generic files.

        Returns ``(images, files)`` with typed media objects.
        """
        from ii_agent.files.media import File as MediaFile, Image

        files_data = await self.get_files_by_ids_and_update_session(
            db, file_ids=file_ids, user_id=user_id, session_id=session_id
        )

        images: list[Image] = []
        files: list[MediaFile] = []

        for file_data in files_data:
            if not file_data.url:
                continue

            files.append(
                MediaFile(
                    id=str(file_data.id),
                    url=file_data.url,
                    filename=file_data.name,
                )
            )

            is_image = file_data.content_type in IMAGE_CONTENT_TYPES
            mime_type = file_data.content_type
            if not is_image and file_data.name:
                ext = file_data.name.rsplit(".", 1)[-1].lower() if "." in file_data.name else ""
                if ext in ("png", "jpg", "jpeg", "gif", "webp", "heic", "heif"):
                    is_image = True
                    if not mime_type or mime_type == "application/octet-stream":
                        mime_type = f"image/{ext}" if ext not in ("jpg",) else "image/jpeg"

            if is_image:
                images.append(Image(url=file_data.url, mime_type=mime_type))

        return images, files
```

Add the import at the top of `service.py` (inside TYPE_CHECKING to avoid circular):

Actually, since `files/media/` is within the `files/` package, use a direct import at the top of the method or a top-level import. Since `media.py` has no dependency on `service.py`, a top-level import is safe:

```python
from ii_agent.files.media import File as MediaFile, Image as MediaImage
```

Add near the top of `service.py` with the other imports.

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest src/tests/unit/files/test_prepare_agent_files_typed.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/ii_agent/files/service.py src/tests/unit/files/test_prepare_agent_files_typed.py
git commit -m "feat: FileService.prepare_agent_files returns typed Image/File objects"
```

---

### Task 5: Create `plans/` domain — types, schemas, exceptions

**Files:**
- Create: `src/ii_agent/plans/__init__.py`
- Create: `src/ii_agent/plans/types.py`
- Create: `src/ii_agent/plans/schemas.py`
- Create: `src/ii_agent/plans/exceptions.py`

- [ ] **Step 1: Create `plans/types.py`**

```python
"""Plan domain enums."""

from enum import StrEnum


class MilestoneStatus(StrEnum):
    """Status of a milestone during plan execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

    @staticmethod
    def terminal_states() -> list[MilestoneStatus]:
        return [MilestoneStatus.COMPLETED, MilestoneStatus.FAILED]
```

- [ ] **Step 2: Create `plans/schemas.py`**

```python
"""Pydantic schemas for the plans domain."""

from __future__ import annotations

from pydantic import BaseModel

from ii_agent.plans.types import MilestoneStatus


class MilestoneSchema(BaseModel):
    """Single milestone within a plan."""

    id: str
    content: str
    details: str = ""
    status: MilestoneStatus = MilestoneStatus.PENDING
    dependencies: list[str] = []


class PlanSchema(BaseModel):
    """Project plan with milestones."""

    summary: str
    milestones: list[MilestoneSchema] = []
```

- [ ] **Step 3: Create `plans/exceptions.py`**

```python
"""Plan domain exceptions."""


class PlanNotFoundError(Exception):
    """Raised when session has no plan in metadata."""

    def __init__(self, session_id: object) -> None:
        super().__init__(f"No plan found for session {session_id}")
        self.session_id = session_id


class MilestoneNotFoundError(Exception):
    """Raised when requested milestone IDs don't exist in the plan."""

    def __init__(self, milestone_ids: list[str]) -> None:
        super().__init__(f"Milestones not found: {milestone_ids}")
        self.milestone_ids = milestone_ids
```

- [ ] **Step 4: Create `plans/__init__.py`**

```python
"""Plans domain — milestone lifecycle management."""

from ii_agent.plans.exceptions import MilestoneNotFoundError, PlanNotFoundError
from ii_agent.plans.schemas import MilestoneSchema, PlanSchema
from ii_agent.plans.types import MilestoneStatus

__all__ = [
    "MilestoneNotFoundError",
    "MilestoneSchema",
    "MilestoneStatus",
    "PlanNotFoundError",
    "PlanSchema",
]
```

Note: `PlanService` will be added to `__init__.py` after it is created in Task 6.

- [ ] **Step 5: Verify imports**

```bash
python -c "from ii_agent.plans import MilestoneStatus, PlanSchema, MilestoneSchema; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add src/ii_agent/plans/
git commit -m "feat: create plans domain with types, schemas, exceptions"
```

---

### Task 6: Create `PlanService` with TDD

**Files:**
- Create: `src/ii_agent/plans/service.py`
- Create: `src/tests/unit/plans/__init__.py`
- Create: `src/tests/unit/plans/test_plan_service.py`
- Modify: `src/ii_agent/plans/__init__.py` (add PlanService export)

- [ ] **Step 1: Create test package**

Create empty `src/tests/unit/plans/__init__.py`.

- [ ] **Step 2: Write failing tests for PlanService**

Create `src/tests/unit/plans/test_plan_service.py`:

```python
"""Unit tests for PlanService."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ii_agent.plans.service import PlanService
from ii_agent.plans.types import MilestoneStatus
from ii_agent.tasks.types import RunStatus


def _make_plan_service() -> tuple[PlanService, MagicMock, MagicMock, AsyncMock]:
    """Create PlanService with mocked dependencies."""
    session_svc = MagicMock()
    event_repo = MagicMock()
    pubsub = AsyncMock()

    svc = PlanService(
        session_service=session_svc,
        event_repo=event_repo,
        pubsub=pubsub,
    )
    return svc, session_svc, event_repo, pubsub


def _plan_context(
    summary: str = "Build a todo app",
    milestones: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    if milestones is None:
        milestones = [
            {"id": "1", "content": "Setup project", "details": "Init repo", "status": "pending"},
            {"id": "2", "content": "Add auth", "details": "JWT login", "status": "pending"},
            {"id": "3", "content": "Add todos", "details": "CRUD", "status": "completed"},
        ]
    return {"summary": summary, "milestones": milestones}


# ── get_milestone_context ─────────────────────────────────────────────


class TestGetMilestoneContext:
    def test_single_milestone_returns_execution_prompt(self) -> None:
        svc, *_ = _make_plan_service()
        ctx = _plan_context()
        result = svc.get_milestone_context(plan_context=ctx, milestone_ids=["1"])

        assert result is not None
        assert "Setup project" in result
        assert "Init repo" in result

    def test_multiple_milestones_returns_combined_context(self) -> None:
        svc, *_ = _make_plan_service()
        ctx = _plan_context()
        result = svc.get_milestone_context(plan_context=ctx, milestone_ids=["1", "2"])

        assert result is not None
        assert "Setup project" in result
        assert "Add auth" in result
        assert "Target Milestones to Build" in result

    def test_no_matching_milestones_returns_none(self) -> None:
        svc, *_ = _make_plan_service()
        ctx = _plan_context()
        result = svc.get_milestone_context(plan_context=ctx, milestone_ids=["99"])

        assert result is None

    def test_empty_plan_context_returns_none(self) -> None:
        svc, *_ = _make_plan_service()
        result = svc.get_milestone_context(plan_context={}, milestone_ids=["1"])

        assert result is None


# ── update_milestones_after_run ───────────────────────────────────────


class TestUpdateMilestonesAfterRun:
    @pytest.mark.asyncio
    async def test_completed_run_marks_milestones_completed(self) -> None:
        svc, session_svc, event_repo, pubsub = _make_plan_service()
        session_id = uuid.uuid4()

        session = MagicMock()
        session.session_metadata = _plan_context()
        session_svc.get_session_by_id = AsyncMock(return_value=session)
        event_repo.save_event = AsyncMock()

        db = AsyncMock()
        await svc.update_milestones_after_run(
            db, session_id=session_id, milestone_ids=["1"], status=RunStatus.COMPLETED
        )

        # Verify milestone status was updated in metadata
        plan = session.session_metadata["plan"] if "plan" in session.session_metadata else session.session_metadata
        milestones = plan.get("milestones", session.session_metadata.get("milestones", []))
        m1 = next(m for m in milestones if m["id"] == "1")
        assert m1["status"] == "completed"

        # Verify event was published
        assert pubsub.publish.called

    @pytest.mark.asyncio
    async def test_failed_run_resets_milestones_to_pending(self) -> None:
        svc, session_svc, event_repo, pubsub = _make_plan_service()
        session_id = uuid.uuid4()

        session = MagicMock()
        session.session_metadata = _plan_context(
            milestones=[
                {"id": "1", "content": "Setup", "details": "", "status": "in_progress"},
            ]
        )
        session_svc.get_session_by_id = AsyncMock(return_value=session)
        event_repo.save_event = AsyncMock()

        db = AsyncMock()
        await svc.update_milestones_after_run(
            db, session_id=session_id, milestone_ids=["1"], status=RunStatus.FAILED
        )

        milestones = session.session_metadata.get("milestones", session.session_metadata.get("plan", {}).get("milestones", []))
        m1 = next((m for m in milestones if m["id"] == "1"), None)
        if m1:
            assert m1["status"] == "pending"

    @pytest.mark.asyncio
    async def test_none_milestone_ids_is_noop(self) -> None:
        svc, session_svc, *_ = _make_plan_service()
        db = AsyncMock()

        await svc.update_milestones_after_run(
            db, session_id=uuid.uuid4(), milestone_ids=None, status=RunStatus.COMPLETED
        )

        session_svc.get_session_by_id.assert_not_called()


# ── reset_milestones_to_pending ───────────────────────────────────────


class TestResetMilestonesToPending:
    @pytest.mark.asyncio
    async def test_resets_specified_milestones(self) -> None:
        svc, session_svc, event_repo, pubsub = _make_plan_service()
        session_id = uuid.uuid4()

        session = MagicMock()
        session.session_metadata = _plan_context(
            milestones=[
                {"id": "1", "content": "Setup", "details": "", "status": "in_progress"},
                {"id": "2", "content": "Auth", "details": "", "status": "in_progress"},
            ]
        )
        session_svc.get_session_by_id = AsyncMock(return_value=session)
        event_repo.save_event = AsyncMock()

        db = AsyncMock()
        await svc.reset_milestones_to_pending(db, session_id=session_id, milestone_ids=["1", "2"])

        milestones = session.session_metadata.get("milestones", session.session_metadata.get("plan", {}).get("milestones", []))
        for m in milestones:
            assert m["status"] == "pending"
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
pytest src/tests/unit/plans/test_plan_service.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'ii_agent.plans.service'`

- [ ] **Step 4: Implement `PlanService`**

Create `src/ii_agent/plans/service.py`:

```python
"""Service layer for plans domain — milestone lifecycle management."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from ii_agent.agents.prompts.plan_mode_prompt import get_milestone_execution_prompt
from ii_agent.core.logger import logger
from ii_agent.plans.types import MilestoneStatus
from ii_agent.realtime.events.app_events import MilestoneUpdatedEvent
from ii_agent.realtime.events.repository import EventRepository
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.sessions.service import SessionService
from ii_agent.tasks.types import RunStatus


class PlanService:
    """Orchestrates milestone execution context and status lifecycle.

    Milestones are stored in ``session.session_metadata["plan"]``.
    This service is the single source of truth for reading and mutating them.
    """

    def __init__(
        self,
        *,
        session_service: SessionService,
        event_repo: EventRepository,
        pubsub: AsyncIOPubSub,
    ) -> None:
        self._session_service = session_service
        self._event_repo = event_repo
        self._pubsub = pubsub

    # ── Public API ────────────────────────────────────────────────────

    def get_milestone_context(
        self,
        plan_context: dict[str, Any],
        milestone_ids: list[str],
    ) -> str | None:
        """Generate AI prompt context for milestone execution."""
        try:
            summary = plan_context.get("summary", "")
            milestones = plan_context.get("milestones", [])

            if not milestones:
                return None

            milestones_text = "\n".join(
                f"  {i + 1}. [{m.get('status', 'pending').upper()}] {m.get('content', '')}"
                for i, m in enumerate(milestones)
            )

            target_milestones = [
                m for m in milestones if str(m.get("id")) in milestone_ids
            ]
            if not target_milestones:
                logger.warning(f"No milestones found matching IDs: {milestone_ids}")
                return None

            if len(target_milestones) == 1:
                milestone = target_milestones[0]
                return get_milestone_execution_prompt(
                    plan_summary=summary,
                    all_milestones=milestones_text,
                    milestone_id=str(milestone.get("id")),
                    milestone_content=milestone.get("content", ""),
                    milestone_details=milestone.get("details", ""),
                )

            target_list = "\n".join(
                f"  - {m.get('content', '')}: {m.get('details', '')}"
                for m in target_milestones
            )
            return f"""# Project Plan Execution

**Project Summary:**
{summary}

**All Milestones:**
{milestones_text}

**Target Milestones to Build:**
{target_list}

**Task:** Build the target milestones listed above. Work through each milestone systematically, ensuring all features are implemented, tested, and integrated.

**Important:**
- Follow the milestone dependencies and order
- Ensure each milestone is fully completed before moving on
- Test each feature as you build it
- Keep the user informed of progress through each milestone
"""

        except Exception as e:
            logger.error(f"Error getting milestone context: {e}")
            return None

    async def update_milestones_after_run(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        milestone_ids: list[str] | None,
        status: RunStatus,
    ) -> None:
        """Update milestone statuses based on run outcome."""
        if not milestone_ids:
            return

        if status == RunStatus.COMPLETED:
            await self._update_milestones_status(
                db, session_id=session_id, milestone_ids=milestone_ids, status=MilestoneStatus.COMPLETED
            )
        elif status in (RunStatus.FAILED, RunStatus.CANCELLED):
            await self._update_milestones_status(
                db, session_id=session_id, milestone_ids=milestone_ids, status=MilestoneStatus.PENDING
            )

    async def reset_milestones_to_pending(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        milestone_ids: list[str],
    ) -> None:
        """Reset milestones to pending status (used on error recovery)."""
        await self._update_milestones_status(
            db, session_id=session_id, milestone_ids=milestone_ids, status=MilestoneStatus.PENDING
        )

    # ── Private ───────────────────────────────────────────────────────

    async def _update_milestones_status(
        self,
        db: AsyncSession,
        *,
        session_id: uuid.UUID,
        milestone_ids: list[str],
        status: MilestoneStatus,
    ) -> None:
        """Mutate session metadata and publish milestone events."""
        try:
            session = await self._session_service.get_session_by_id(db, session_id)
            if not session or not session.session_metadata:
                return

            plan = session.session_metadata.get("plan", {})
            milestones = plan.get("milestones", [])

            for milestone in milestones:
                if str(milestone.get("id")) not in milestone_ids:
                    continue

                milestone["status"] = str(status)

                event = MilestoneUpdatedEvent(
                    session_id=session_id,
                    content={"milestone_id": milestone.get("id"), "status": str(status)},
                    milestone_id=str(milestone.get("id", "")),
                    status=status if status in (
                        MilestoneStatus.PENDING,
                        MilestoneStatus.IN_PROGRESS,
                        MilestoneStatus.COMPLETED,
                        MilestoneStatus.FAILED,
                    ) else MilestoneStatus.PENDING,
                )
                await self._event_repo.save_event(
                    db, session_id=session_id, event=event
                )
                await self._pubsub.publish(event)

            session.session_metadata = {**session.session_metadata, "plan": plan}
            db.add(session)
            await db.commit()

        except Exception as e:
            logger.error(f"Error updating milestones status: {e}")
```

- [ ] **Step 5: Update `plans/__init__.py` to export PlanService**

Add to `src/ii_agent/plans/__init__.py`:

```python
from ii_agent.plans.service import PlanService
```

And add `"PlanService"` to `__all__`.

- [ ] **Step 6: Run tests to verify they pass**

```bash
pytest src/tests/unit/plans/test_plan_service.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/ii_agent/plans/service.py src/ii_agent/plans/__init__.py src/tests/unit/plans/
git commit -m "feat: implement PlanService with milestone lifecycle management"
```

---

### Task 7: Wire `PlanService` into `ApplicationContainer`

**Files:**
- Modify: `src/ii_agent/core/container.py`

- [ ] **Step 1: Add PlanService import and field**

In `src/ii_agent/core/container.py`:

Add import near the other service imports:
```python
from ii_agent.plans.service import PlanService
```

Add field to `ApplicationContainer` dataclass (after `sandbox_service`):
```python
    plan_service: PlanService
```

- [ ] **Step 2: Create PlanService in `init()` method**

Inside `ApplicationContainer.init()`, after `sandbox_svc` is created, add:

```python
        plan_svc = PlanService(
            session_service=session_svc,
            event_repo=event_repo,
            pubsub=None,  # Set later by lifespan after pubsub is created
        )
```

Note: `pubsub` is not available at container init time — it's created in `lifespan.py` after the container. We need to set it later. Add to the return statement:

```python
            plan_service=plan_svc,
```

- [ ] **Step 3: Verify PlanService pubsub injection approach**

Check `src/ii_agent/app/lifespan.py` to see where pubsub is wired. The pubsub reference will need to be set on PlanService after pubsub creation. Add a setter or make `pubsub` a mutable attribute.

Actually, looking at the base handler pattern: handlers receive `pubsub` in their constructor and it's available when handlers are created (after pubsub init in lifespan). The PlanService needs pubsub for event publishing.

Approach: Accept `pubsub` as `AsyncIOPubSub | None = None` in PlanService constructor. In `lifespan.py`, set `container.plan_service._pubsub = pubsub` after pubsub is created. Or better: make PlanService accept it via a `set_pubsub()` method.

Simpler approach: since `_update_milestones_status` already takes `db` (implying it's called within a request context), and the handler already has `pubsub`, pass pubsub as a parameter to the methods that need it, or have the handler call `send_event` after the service does its work.

**Cleanest approach:** PlanService returns events to publish, handler publishes them. This follows SRP — service manages state, handler manages I/O.

Update PlanService `_update_milestones_status` to return list of events instead of publishing them directly. The handler calls `send_event` for each.

Wait — this creates coupling. Let's keep it simpler: make pubsub a required constructor arg. In lifespan, create PlanService AFTER pubsub, or pass pubsub into container init.

Let me check how container is wired with pubsub in lifespan.

Actually the simplest path: add a `set_pubsub` method on PlanService. Container creates PlanService with `pubsub=None`. Lifespan sets it after pubsub is created. This matches the pattern where container is created first, then pubsub.

- [ ] **Step 4: Verify import and wiring works**

```bash
python -c "from ii_agent.core.container import ApplicationContainer; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/ii_agent/core/container.py
git commit -m "feat: wire PlanService into ApplicationContainer"
```

---

### Task 8: Set PlanService pubsub in lifespan

**Files:**
- Modify: `src/ii_agent/app/lifespan.py`
- Modify: `src/ii_agent/plans/service.py` (add `set_pubsub` method)

- [ ] **Step 1: Add `set_pubsub` to PlanService**

In `src/ii_agent/plans/service.py`, update constructor and add method:

```python
    def __init__(
        self,
        *,
        session_service: SessionService,
        event_repo: EventRepository,
        pubsub: AsyncIOPubSub | None = None,
    ) -> None:
        self._session_service = session_service
        self._event_repo = event_repo
        self._pubsub = pubsub

    def set_pubsub(self, pubsub: AsyncIOPubSub) -> None:
        """Set the pubsub instance (called by lifespan after pubsub is created)."""
        self._pubsub = pubsub
```

- [ ] **Step 2: Wire pubsub in lifespan**

In `src/ii_agent/app/lifespan.py`, after the line that creates pubsub and before `SocketIOManager`, add:

```python
    container.plan_service.set_pubsub(pubsub)
```

(Find the exact location by searching for where `pubsub` or `AsyncIOPubSub` is created in lifespan.)

- [ ] **Step 3: Commit**

```bash
git add src/ii_agent/plans/service.py src/ii_agent/app/lifespan.py
git commit -m "feat: wire PlanService pubsub via lifespan"
```

---

### Task 9: Refactor `query.py` — remove domain logic, delegate to services

**Files:**
- Modify: `src/ii_agent/realtime/handlers/query.py`

- [ ] **Step 1: Remove milestone and file upload methods, delegate to services**

Replace the full content of `query.py` with the refactored version.

Key changes:
1. Remove `_handle_file_upload` — use `file_service.prepare_agent_files()`
2. Remove `_get_milestone_context` — use `plan_service.get_milestone_context()`
3. Remove `_update_milestones_after_run` — use `plan_service.update_milestones_after_run()`
4. Remove `_update_milestones_status` — moved to PlanService
5. Remove `IMAGE_CONTENT_TYPES` and `SEVEN_DAY_SECONDS` constants — no longer needed
6. Update imports: `from ii_agent.files.media import Image, File as UrlFile`

Refactored `query.py`:

```python
"""Handler for query command that processes user queries and runs agents."""

from __future__ import annotations

import uuid
from typing import Any

from ii_agent.agents.factory.converter import convert_agent_event_to_realtime
from ii_agent.agents.runs.agent import RunCompletedEvent, RunOutput
from ii_agent.agents.sandboxes import upload_media_to_sandbox
from ii_agent.agents.types import AgentType
from ii_agent.core.container import ApplicationContainer
from ii_agent.core.db import get_db_session_local
from ii_agent.core.logger import logger
from ii_agent.files.media import File as UrlFile, Image
from ii_agent.realtime.events.app_events import AgentRunEvent
from ii_agent.realtime.handlers.base import BaseCommandHandler, CommandType
from ii_agent.realtime.pubsub import AsyncIOPubSub
from ii_agent.realtime.schemas import InitAgentContent, QueryCommandContent
from ii_agent.sessions.schemas import SessionInfo
from ii_agent.tasks.types import RunStatus
from ii_agent.agents.factory.agent import agent_factory


class UserQueryHandler(BaseCommandHandler[QueryCommandContent]):
    """Handler for query command that processes user queries and runs agents."""

    _content_type = QueryCommandContent

    def __init__(self, pubsub: AsyncIOPubSub, container: ApplicationContainer) -> None:
        super().__init__(pubsub=pubsub, container=container)

    def get_command_type(self) -> CommandType:
        return CommandType.QUERY

    async def handle(self, content: QueryCommandContent, existing_session: SessionInfo) -> None:
        """Handle query processing by creating ChatSessionContext and running the agent."""
        query_command = content

        is_valid, session_info, llm_config = await self.validate_and_update_session(
            existing_session, query_command, min_credits=1.0
        )
        if not is_valid or not session_info:
            return

        await self._handle_query(query_command, session_info)

    async def _handle_query(
        self, query_command: QueryCommandContent, session_info: SessionInfo
    ) -> None:
        """Handle query processing for v1 API."""
        plan_service = self._container.plan_service
        file_service = self._container.file_service

        milestone_context = None
        if query_command.milestone_ids and query_command.plan_context:
            milestone_context = plan_service.get_milestone_context(
                plan_context=query_command.plan_context,
                milestone_ids=query_command.milestone_ids,
            )

        run_service = self._container.run_task_service
        try:
            async with get_db_session_local() as db:
                run_task = await run_service.claim_task(db, session_id=session_info.id)
        except Exception as e:
            logger.error(f"Failed to claim task: {e}", exc_info=True)
            await self._send_error_event(
                session_id=session_info.id,
                message=str(e),
                error_type="internal",
            )
            return

        final_status = RunStatus.FAILED
        try:
            init_content = InitAgentContent(
                model_id=query_command.model_id,
                tool_args=query_command.tool_args,
                source=query_command.source,
                thinking_tokens=query_command.thinking_tokens,
                agent_type=session_info.agent_type,
                metadata=query_command.metadata,
            )

            llm_config = await self._get_llm_settings(
                session=session_info,
                source=init_content.source,
                model_id=init_content.model_id,
            )

            agent = await agent_factory.create_agent(
                user_id=str(session_info.user_id),
                session_id=str(session_info.id),
                llm_config=llm_config,
                agent_type=AgentType(session_info.agent_type) if session_info.agent_type else AgentType.GENERAL,
                tool_args=init_content.tool_args,
                metadata=init_content.metadata,
            )

            # Prepare files via FileService
            images: list[Image] = []
            files: list[UrlFile] = []
            if query_command.files:
                async with get_db_session_local() as db:
                    images, files = await file_service.prepare_agent_files(
                        db,
                        file_ids=query_command.files,
                        user_id=session_info.user_id,
                        session_id=session_info.id,
                    )

            # Pre-upload media to sandbox so the agent gets sandbox paths
            if images or files:
                sandbox_service = self._container.sandbox_service
                async with get_db_session_local() as db:
                    sandbox = await sandbox_service.init_sandbox(
                        db,
                        session_id=session_info.id,
                        user_id=session_info.user_id,
                    )
                agent.sandbox = sandbox
                await sandbox.create_directory(sandbox.upload_path, exist_ok=True)
                sandbox_files, sandbox_images = await upload_media_to_sandbox(
                    sandbox=sandbox,
                    files=files or [],
                    images=images or [],
                    upload_path=sandbox.upload_path,
                )
                if sandbox_files:
                    files = sandbox_files
                if sandbox_images:
                    images = sandbox_images

            # Build instruction text with milestone context if available
            instruction_text = query_command.text
            if milestone_context:
                instruction_text = f"{milestone_context}\n\nUser instruction: {query_command.text}"

            event_stream = await agent.arun(
                instruction_text,
                stream=True,
                stream_events=True,
                run_id=str(run_task.id),
                images=images or None,
                files=files or None,
                yield_run_output=False,
            )

            async for event in event_stream:
                app_event = AgentRunEvent.from_run_output_event(event=event)
                await self.send_event(app_event)

            # Update milestones after successful run
            async with get_db_session_local() as db:
                await plan_service.update_milestones_after_run(
                    db,
                    session_id=session_info.id,
                    milestone_ids=query_command.milestone_ids,
                    status=final_status,
                )

        except Exception as e:
            logger.error(f"Error processing v1 query: {e}", exc_info=True)
            # Reset milestones to pending on error
            if query_command.milestone_ids:
                async with get_db_session_local() as db:
                    await plan_service.reset_milestones_to_pending(
                        db,
                        session_id=session_info.id,
                        milestone_ids=query_command.milestone_ids,
                    )
            raise
```

- [ ] **Step 2: Verify handler imports resolve**

```bash
python -c "from ii_agent.realtime.handlers.query import UserQueryHandler; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/ii_agent/realtime/handlers/query.py
git commit -m "refactor: query handler delegates to PlanService and FileService"
```

---

### Task 10: Update `plan.py` handler imports

**Files:**
- Modify: `src/ii_agent/realtime/handlers/plan.py`

- [ ] **Step 1: Update media imports and remove duplicate constants**

In `src/ii_agent/realtime/handlers/plan.py`:

Replace:
```python
from ii_agent.agents.media import Image, File as UrlFile
```
with:
```python
from ii_agent.files.media import Image, File as UrlFile
```

Remove the duplicate constants (already in FileService):
```python
# Remove these lines:
IMAGE_CONTENT_TYPES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
SEVEN_DAY_SECONDS = 7 * 24 * 3600
```

- [ ] **Step 2: Update `_handle_file_upload_v1` to use FileService**

Replace the `_handle_file_upload_v1` method with delegation to `file_service.prepare_agent_files()`:

```python
    async def _handle_file_upload_v1(
        self,
        query_command: QueryCommandContent,
        session_info: SessionInfo,
    ) -> tuple[list[Image], list[UrlFile]]:
        """Handle file uploads for v1 agent with signed URLs."""
        if not query_command.files:
            return [], []

        file_svc = self._container.file_service

        async with get_db_session_local() as db:
            images, files = await file_svc.prepare_agent_files(
                db,
                file_ids=query_command.files,
                user_id=session_info.user_id,
                session_id=session_info.id,
            )

        return images, files
```

- [ ] **Step 3: Verify handler imports resolve**

```bash
python -c "from ii_agent.realtime.handlers.plan import PlanHandler; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/ii_agent/realtime/handlers/plan.py
git commit -m "refactor: plan handler uses FileService for file uploads"
```

---

### Task 11: Run full test suite and fix any remaining issues

**Files:**
- All modified files

- [ ] **Step 1: Run plans domain tests**

```bash
pytest src/tests/unit/plans/ -v
```

Expected: PASS

- [ ] **Step 2: Run files domain tests**

```bash
pytest src/tests/unit/files/ -v
```

Expected: PASS

- [ ] **Step 3: Run realtime handler tests**

```bash
pytest src/tests/unit/realtime/ -v
```

Expected: PASS (or identify failures to fix)

- [ ] **Step 4: Run engine tests (media imports)**

```bash
pytest src/tests/unit/engine/ -v --timeout=60
```

Expected: PASS

- [ ] **Step 5: Run full test suite**

```bash
pytest src/tests/unit/ -v --timeout=120
```

Expected: All PASS

- [ ] **Step 6: Fix any failures found**

Address any test failures by updating imports or adjusting mocks.

- [ ] **Step 7: Final commit**

```bash
git add -u
git commit -m "fix: resolve test failures from query handler refactoring"
```
