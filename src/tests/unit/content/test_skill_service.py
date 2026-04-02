from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from ii_agent.content.skills.exceptions import BuiltinSkillDeleteError
from ii_agent.content.skills.models import SkillSource
from ii_agent.content.skills.service import SkillService


class FakeSkillRepo:
    def __init__(self):
        self.skills_by_id = {}
        self.user_overrides = {}
        self.deleted = []
        self.created = []

    async def get_by_name_and_user(self, db, skill_name, user_id):
        return None

    async def list_by_user(self, db, user_id):
        return list(self.user_overrides.values())

    async def list_builtin(self, db):
        return [self.skills_by_id["builtin-1"]]

    async def get_by_id_for_user(self, db, skill_id, user_id):
        return None

    async def get_by_id(self, db, skill_id):
        return self.skills_by_id.get(skill_id)

    async def get_user_builtin_override(self, db, user_id, name):
        return self.user_overrides.get((user_id, name))

    async def create(self, db, skill):
        self.created.append(skill)
        self.user_overrides[(skill.user_id, skill.name)] = skill
        return skill

    async def update(self, db, skill):
        self.user_overrides[(skill.user_id, skill.name)] = skill
        return skill

    async def get_user_skill(self, db, skill_id, user_id):
        skill = self.skills_by_id.get(skill_id)
        if skill and skill.user_id == user_id:
            return skill
        return None

    async def get_builtin_by_id(self, db, skill_id):
        skill = self.skills_by_id.get(skill_id)
        if skill and skill.user_id is None:
            return skill
        return None

    async def delete(self, db, skill):
        self.deleted.append(skill)


@pytest.fixture
def builtin_skill():
    return SimpleNamespace(
        id="builtin-1",
        user_id=None,
        name="builtin-docx",
        description="Built in",
        source=SkillSource.BUILTIN.value,
        source_url=None,
        sandbox_path="/workspace/.skills/builtin-docx",
        storage_uri="gs://bucket/builtin-docx",
        license=None,
        compatibility=None,
        is_enabled=True,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_toggle_builtin_skill_creates_disabled_override(settings_factory, builtin_skill):
    repo = FakeSkillRepo()
    repo.skills_by_id[builtin_skill.id] = builtin_skill

    service = SkillService(skill_repo=repo, config=settings_factory())

    info = await service.toggle_skill(
        db=None,
        skill_id=builtin_skill.id,
        user_id="u1",
        is_enabled=False,
    )

    assert info is not None
    assert info.is_enabled is False
    assert len(repo.created) == 1


@pytest.mark.asyncio
async def test_toggle_builtin_skill_reenable_removes_override(settings_factory, builtin_skill):
    repo = FakeSkillRepo()
    repo.skills_by_id[builtin_skill.id] = builtin_skill
    override = SimpleNamespace(
        id="ovr-1",
        user_id="u1",
        name=builtin_skill.name,
        is_enabled=False,
        updated_at=datetime.now(timezone.utc),
    )
    repo.user_overrides[("u1", builtin_skill.name)] = override

    service = SkillService(skill_repo=repo, config=settings_factory())

    info = await service.toggle_skill(
        db=None,
        skill_id=builtin_skill.id,
        user_id="u1",
        is_enabled=True,
    )

    assert info.is_enabled is True
    assert repo.deleted[0] is override


@pytest.mark.asyncio
async def test_delete_skill_blocks_builtin_deletes(settings_factory, builtin_skill):
    repo = FakeSkillRepo()
    repo.skills_by_id[builtin_skill.id] = builtin_skill

    service = SkillService(skill_repo=repo, config=settings_factory())

    with pytest.raises(BuiltinSkillDeleteError):
        await service.delete_skill(
            db=None,
            skill_id=builtin_skill.id,
            user_id="u1",
        )
