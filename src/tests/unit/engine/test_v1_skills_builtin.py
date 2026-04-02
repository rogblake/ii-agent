"""Unit tests for v1 skills framework.

Covers:
- skills_ref parser (parse_frontmatter, read_properties, find_skill_md)
- skills_ref models (SkillProperties)
- skills_ref errors
- builtin skills directory discovery
- skills loader (load_builtin_skills)
- get_user_skills merge logic (mocked DB)
- get_skill_by_name (mocked DB)
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


# ===========================================================================
# skills_ref errors
# ===========================================================================


class TestSkillErrors:
    def test_parse_error_is_skill_error(self):
        from ii_agent.settings.skills.skills_ref.errors import ParseError, SkillError

        err = ParseError("Bad parse")
        assert isinstance(err, SkillError)
        assert str(err) == "Bad parse"

    def test_validation_error_stores_errors_list(self):
        from ii_agent.settings.skills.skills_ref.errors import ValidationError

        err = ValidationError("Missing name", errors=["Missing name", "Also wrong"])
        assert err.errors == ["Missing name", "Also wrong"]

    def test_validation_error_defaults_errors_from_message(self):
        from ii_agent.settings.skills.skills_ref.errors import ValidationError

        err = ValidationError("Oops")
        assert err.errors == ["Oops"]


# ===========================================================================
# SkillProperties model
# ===========================================================================


class TestSkillProperties:
    def test_to_dict_basic(self):
        from ii_agent.settings.skills.skills_ref.models import SkillProperties

        props = SkillProperties(name="my-skill", description="Does stuff")
        d = props.to_dict()
        assert d["name"] == "my-skill"
        assert d["description"] == "Does stuff"

    def test_to_dict_excludes_none_license(self):
        from ii_agent.settings.skills.skills_ref.models import SkillProperties

        props = SkillProperties(name="s", description="d")
        d = props.to_dict()
        assert "license" not in d

    def test_to_dict_includes_license_when_set(self):
        from ii_agent.settings.skills.skills_ref.models import SkillProperties

        props = SkillProperties(name="s", description="d", license="MIT")
        d = props.to_dict()
        assert d["license"] == "MIT"

    def test_to_dict_includes_compatibility_when_set(self):
        from ii_agent.settings.skills.skills_ref.models import SkillProperties

        props = SkillProperties(name="s", description="d", compatibility=">=1.0")
        d = props.to_dict()
        assert d["compatibility"] == ">=1.0"

    def test_to_dict_excludes_empty_metadata(self):
        from ii_agent.settings.skills.skills_ref.models import SkillProperties

        props = SkillProperties(name="s", description="d")
        d = props.to_dict()
        assert "metadata" not in d

    def test_to_dict_includes_non_empty_metadata(self):
        from ii_agent.settings.skills.skills_ref.models import SkillProperties

        props = SkillProperties(name="s", description="d", metadata={"key": "val"})
        d = props.to_dict()
        assert d["metadata"] == {"key": "val"}

    def test_to_dict_allowed_tools_key_with_hyphen(self):
        from ii_agent.settings.skills.skills_ref.models import SkillProperties

        props = SkillProperties(name="s", description="d", allowed_tools="Bash Read")
        d = props.to_dict()
        assert "allowed-tools" in d
        assert d["allowed-tools"] == "Bash Read"


# ===========================================================================
# parse_frontmatter
# ===========================================================================


class TestParseFrontmatter:
    def test_valid_frontmatter_returns_metadata_and_body(self):
        from ii_agent.settings.skills.skills_ref.parser import parse_frontmatter

        content = "---\nname: my-skill\ndescription: Does stuff\n---\nBody content"
        metadata, body = parse_frontmatter(content)
        assert metadata["name"] == "my-skill"
        assert body == "Body content"

    def test_missing_frontmatter_raises_parse_error(self):
        from ii_agent.settings.skills.skills_ref.errors import ParseError
        from ii_agent.settings.skills.skills_ref.parser import parse_frontmatter

        with pytest.raises(ParseError, match="frontmatter"):
            parse_frontmatter("No frontmatter here")

    def test_unclosed_frontmatter_raises_parse_error(self):
        from ii_agent.settings.skills.skills_ref.errors import ParseError
        from ii_agent.settings.skills.skills_ref.parser import parse_frontmatter

        with pytest.raises(ParseError, match="frontmatter"):
            parse_frontmatter("---\nname: my-skill\n")

    def test_invalid_yaml_raises_parse_error(self):
        from ii_agent.settings.skills.skills_ref.errors import ParseError
        from ii_agent.settings.skills.skills_ref.parser import parse_frontmatter

        with pytest.raises(ParseError, match="YAML"):
            parse_frontmatter("---\n: invalid: yaml: content\n---\nBody")

    def test_metadata_nested_dict_converted_to_str_values(self):
        from ii_agent.settings.skills.skills_ref.parser import parse_frontmatter

        # metadata field is a nested dict whose values must be strings
        content = "---\nname: s\ndescription: d\nmetadata:\n  key: value\n---\n"
        metadata, _ = parse_frontmatter(content)
        # metadata sub-dict values should all be strings
        assert isinstance(metadata["metadata"]["key"], str)


# ===========================================================================
# find_skill_md
# ===========================================================================


class TestFindSkillMd:
    def test_returns_path_when_skill_md_exists(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.parser import find_skill_md

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text("---\nname: s\n---\n")

        result = find_skill_md(skill_dir)
        assert result == skill_md

    def test_returns_lowercase_skill_md_if_no_uppercase(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.parser import find_skill_md

        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        skill_md = skill_dir / "skill.md"
        skill_md.write_text("---\nname: s\n---\n")

        result = find_skill_md(skill_dir)
        assert result == skill_md

    def test_returns_none_when_no_skill_md(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.parser import find_skill_md

        skill_dir = tmp_path / "empty-skill"
        skill_dir.mkdir()

        result = find_skill_md(skill_dir)
        assert result is None


# ===========================================================================
# read_properties
# ===========================================================================


class TestReadProperties:
    def _make_skill_dir(self, tmp_path, content: str, filename="SKILL.md"):
        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / filename).write_text(content)
        return skill_dir

    def test_reads_name_and_description(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.parser import read_properties

        content = "---\nname: test-skill\ndescription: A test skill\n---\nBody"
        skill_dir = self._make_skill_dir(tmp_path, content)
        props = read_properties(skill_dir)
        assert props.name == "test-skill"
        assert props.description == "A test skill"

    def test_missing_skill_md_raises_parse_error(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.errors import ParseError
        from ii_agent.settings.skills.skills_ref.parser import read_properties

        skill_dir = tmp_path / "empty"
        skill_dir.mkdir()
        with pytest.raises(ParseError, match="SKILL.md"):
            read_properties(skill_dir)

    def test_missing_name_raises_validation_error(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.errors import ValidationError
        from ii_agent.settings.skills.skills_ref.parser import read_properties

        content = "---\ndescription: No name here\n---\n"
        skill_dir = self._make_skill_dir(tmp_path, content)
        with pytest.raises(ValidationError, match="name"):
            read_properties(skill_dir)

    def test_missing_description_raises_validation_error(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.errors import ValidationError
        from ii_agent.settings.skills.skills_ref.parser import read_properties

        content = "---\nname: skill-name\n---\n"
        skill_dir = self._make_skill_dir(tmp_path, content)
        with pytest.raises(ValidationError, match="description"):
            read_properties(skill_dir)

    def test_empty_name_raises_validation_error(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.errors import ValidationError
        from ii_agent.settings.skills.skills_ref.parser import read_properties

        content = "---\nname: '   '\ndescription: ok\n---\n"
        skill_dir = self._make_skill_dir(tmp_path, content)
        with pytest.raises(ValidationError):
            read_properties(skill_dir)

    def test_reads_optional_license(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.parser import read_properties

        content = "---\nname: sk\ndescription: d\nlicense: MIT\n---\n"
        skill_dir = self._make_skill_dir(tmp_path, content)
        props = read_properties(skill_dir)
        assert props.license == "MIT"

    def test_reads_optional_compatibility(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.parser import read_properties

        content = "---\nname: sk\ndescription: d\ncompatibility: '>=2.0'\n---\n"
        skill_dir = self._make_skill_dir(tmp_path, content)
        props = read_properties(skill_dir)
        assert props.compatibility == ">=2.0"

    def test_reads_allowed_tools(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.parser import read_properties

        content = "---\nname: sk\ndescription: d\nallowed-tools: Bash Read\n---\n"
        skill_dir = self._make_skill_dir(tmp_path, content)
        props = read_properties(skill_dir)
        assert props.allowed_tools == "Bash Read"

    def test_trims_whitespace_from_name_description(self, tmp_path):
        from ii_agent.settings.skills.skills_ref.parser import read_properties

        content = "---\nname: '  my-skill  '\ndescription: '  My desc  '\n---\n"
        skill_dir = self._make_skill_dir(tmp_path, content)
        props = read_properties(skill_dir)
        assert props.name == "my-skill"
        assert props.description == "My desc"


# ===========================================================================
# builtin skills directory discovery
# ===========================================================================


class TestBuiltinSkillsDirectory:
    def test_get_builtin_skill_dirs_returns_directories_with_skill_md(self):
        from ii_agent.settings.skills.builtin import get_builtin_skill_dirs

        dirs = get_builtin_skill_dirs()
        # Should return a non-empty list
        assert isinstance(dirs, list)
        assert len(dirs) > 0

    def test_all_returned_dirs_have_skill_md(self):
        from ii_agent.settings.skills.builtin import get_builtin_skill_dirs

        for skill_dir in get_builtin_skill_dirs():
            assert (skill_dir / "SKILL.md").exists(), f"{skill_dir} has no SKILL.md"

    def test_get_builtin_skill_upath_returns_correct_path(self):
        from ii_agent.settings.skills.builtin import get_builtin_skill_upath

        path = get_builtin_skill_upath("pdf")
        assert "pdf" in str(path)


# ===========================================================================
# load_builtin_skills
# ===========================================================================


class TestLoadBuiltinSkills:
    def test_returns_non_empty_list(self):
        from ii_agent.settings.skills.loader import load_builtin_skills

        skills = load_builtin_skills()
        assert isinstance(skills, list)
        assert len(skills) > 0

    def test_each_skill_has_required_keys(self):
        from ii_agent.settings.skills.loader import load_builtin_skills

        skills = load_builtin_skills()
        required_keys = {
            "name",
            "description",
            "skill_md_content",
            "source",
            "sandbox_path",
            "storage_uri",
        }
        for skill in skills:
            missing = required_keys - set(skill.keys())
            assert not missing, f"Skill {skill.get('name')} missing keys: {missing}"

    def test_storage_uri_uses_builtin_prefix(self):
        from ii_agent.settings.skills.loader import load_builtin_skills

        skills = load_builtin_skills()
        for skill in skills:
            assert skill["storage_uri"].startswith("builtin:"), (
                f"Expected builtin: prefix, got {skill['storage_uri']}"
            )

    def test_sandbox_path_starts_with_workspace_skills(self):
        from ii_agent.settings.skills.loader import load_builtin_skills

        skills = load_builtin_skills()
        for skill in skills:
            assert "/workspace/.skills/" in skill["sandbox_path"]

    def test_skill_md_content_is_non_empty_string(self):
        from ii_agent.settings.skills.loader import load_builtin_skills

        skills = load_builtin_skills()
        for skill in skills:
            assert isinstance(skill["skill_md_content"], str)
            assert len(skill["skill_md_content"]) > 0

    def test_skill_names_are_strings(self):
        from ii_agent.settings.skills.loader import load_builtin_skills

        skills = load_builtin_skills()
        for skill in skills:
            assert isinstance(skill["name"], str)
            assert len(skill["name"]) > 0

    def test_allowed_tools_is_list(self):
        from ii_agent.settings.skills.loader import load_builtin_skills

        skills = load_builtin_skills()
        for skill in skills:
            assert isinstance(skill["allowed_tools"], list)


# ===========================================================================
# get_user_skills
# ===========================================================================


class TestGetUserSkills:
    """Tests for the merge logic in get_user_skills (DB mocked)."""

    def _make_skill(self, name, user_id=None, is_enabled=True):
        s = SimpleNamespace()
        s.name = name
        s.user_id = user_id
        s.is_enabled = is_enabled
        return s

    async def test_user_skill_overrides_builtin(self):
        from ii_agent.settings.skills.loader import get_user_skills

        builtin = self._make_skill("pdf", user_id=None, is_enabled=True)
        user_override = self._make_skill("pdf", user_id="u1", is_enabled=True)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [builtin, user_override]
        mock_db.execute = AsyncMock(return_value=mock_result)

        skills = await get_user_skills(mock_db, user_id="u1")
        # user override should take precedence - expect exactly 1 skill named pdf
        pdf_skills = [s for s in skills if s.name == "pdf"]
        assert len(pdf_skills) == 1
        assert pdf_skills[0].user_id == "u1"

    async def test_disabled_user_skill_hidden_when_enabled_only(self):
        from ii_agent.settings.skills.loader import get_user_skills

        builtin = self._make_skill("docx", user_id=None, is_enabled=True)
        user_disabled = self._make_skill("docx", user_id="u1", is_enabled=False)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [builtin, user_disabled]
        mock_db.execute = AsyncMock(return_value=mock_result)

        skills = await get_user_skills(mock_db, user_id="u1", enabled_only=True)
        docx_skills = [s for s in skills if s.name == "docx"]
        # The user override (disabled) takes precedence over enabled builtin
        assert len(docx_skills) == 0

    async def test_uuid_user_override_matches_string_user_id(self):
        from ii_agent.settings.skills.loader import get_user_skills

        user_id = uuid.uuid4()
        builtin = self._make_skill("pdf", user_id=None, is_enabled=True)
        user_override = self._make_skill("pdf", user_id=user_id, is_enabled=True)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [builtin, user_override]
        mock_db.execute = AsyncMock(return_value=mock_result)

        skills = await get_user_skills(mock_db, user_id=str(user_id))
        pdf_skills = [s for s in skills if s.name == "pdf"]
        assert len(pdf_skills) == 1
        assert pdf_skills[0].user_id == user_id

    async def test_enabled_only_false_returns_disabled_skills(self):
        from ii_agent.settings.skills.loader import get_user_skills

        builtin = self._make_skill("docx", user_id=None, is_enabled=False)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [builtin]
        mock_db.execute = AsyncMock(return_value=mock_result)

        skills = await get_user_skills(mock_db, user_id="u1", enabled_only=False)
        assert len(skills) == 1

    async def test_multiple_builtin_skills_all_returned(self):
        from ii_agent.settings.skills.loader import get_user_skills

        skills_list = [
            self._make_skill("pdf", user_id=None),
            self._make_skill("docx", user_id=None),
            self._make_skill("pptx", user_id=None),
        ]

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = skills_list
        mock_db.execute = AsyncMock(return_value=mock_result)

        skills = await get_user_skills(mock_db, user_id="u1")
        assert len(skills) == 3


# ===========================================================================
# get_skill_by_name
# ===========================================================================


class TestGetSkillByName:
    def _make_skill(self, name, user_id=None, is_enabled=True):
        s = SimpleNamespace()
        s.name = name
        s.user_id = user_id
        s.is_enabled = is_enabled
        return s

    async def test_returns_enabled_user_skill(self):
        from ii_agent.settings.skills.loader import get_skill_by_name

        user_skill = self._make_skill("pdf", user_id="u1", is_enabled=True)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user_skill
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_skill_by_name(mock_db, user_id="u1", skill_name="pdf")
        assert result is not None
        assert result.user_id == "u1"

    async def test_returns_none_for_disabled_user_skill(self):
        from ii_agent.settings.skills.loader import get_skill_by_name

        user_disabled = self._make_skill("pdf", user_id="u1", is_enabled=False)

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user_disabled
        mock_db.execute = AsyncMock(return_value=mock_result)

        result = await get_skill_by_name(mock_db, user_id="u1", skill_name="pdf")
        assert result is None

    async def test_falls_back_to_builtin_when_no_user_override(self):
        from ii_agent.settings.skills.loader import get_skill_by_name

        builtin_skill = self._make_skill("docx", user_id=None, is_enabled=True)

        call_count = 0
        mock_db = AsyncMock()

        async def execute_side_effect(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if call_count == 1:
                # First call: user skill lookup -> None
                mock_result.scalar_one_or_none.return_value = None
            else:
                # Second call: builtin lookup
                mock_result.scalar_one_or_none.return_value = builtin_skill
            return mock_result

        mock_db.execute = execute_side_effect

        result = await get_skill_by_name(mock_db, user_id="u1", skill_name="docx")
        assert result is not None
        assert result.user_id is None
