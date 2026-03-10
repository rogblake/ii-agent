"""Unit tests for engine/runtime/skills/ - SkillCreator base, Skill model, SkillProperties, validator."""

from pathlib import Path
from typing import Optional

import pytest

from ii_agent.agent.runtime.skills.base import SkillCreator
from ii_agent.agent.runtime.skills.skills_ref.models import Skill, SkillProperties, SkillSource
from ii_agent.agent.runtime.skills.skills_ref.validator import (
    MAX_COMPATIBILITY_LENGTH,
    MAX_DESCRIPTION_LENGTH,
    MAX_SKILL_NAME_LENGTH,
    _validate_compatibility,
    _validate_description,
    _validate_metadata_fields,
    _validate_name,
    validate_metadata,
)


# ---------------------------------------------------------------------------
# SkillSource tests
# ---------------------------------------------------------------------------


class TestSkillSource:
    """Tests for SkillSource enum."""

    def test_builtin_value(self):
        assert SkillSource.BUILDIN == "builtin"

    def test_git_value(self):
        assert SkillSource.GIT == "git"

    def test_is_string_enum(self):
        assert isinstance(SkillSource.BUILDIN, str)

    def test_comparison_with_string(self):
        assert SkillSource.BUILDIN == "builtin"
        assert SkillSource.GIT == "git"


# ---------------------------------------------------------------------------
# SkillProperties tests
# ---------------------------------------------------------------------------


class TestSkillProperties:
    """Tests for SkillProperties dataclass."""

    def test_basic_construction(self):
        props = SkillProperties(name="my-skill", description="Does something useful")
        assert props.name == "my-skill"
        assert props.description == "Does something useful"

    def test_optional_fields_default_none(self):
        props = SkillProperties(name="skill", description="desc")
        assert props.license is None
        assert props.compatibility is None
        assert props.allowed_tools is None

    def test_metadata_defaults_to_empty_dict(self):
        props = SkillProperties(name="skill", description="desc")
        assert props.metadata == {}

    def test_with_all_fields(self):
        props = SkillProperties(
            name="full-skill",
            description="Full description",
            license="MIT",
            compatibility=">=1.0",
            allowed_tools="bash,python",
            metadata={"key": "value"},
        )
        assert props.license == "MIT"
        assert props.compatibility == ">=1.0"
        assert props.allowed_tools == "bash,python"
        assert props.metadata == {"key": "value"}

    def test_to_dict_basic(self):
        props = SkillProperties(name="my-skill", description="My description")
        d = props.to_dict()
        assert d["name"] == "my-skill"
        assert d["description"] == "My description"

    def test_to_dict_excludes_none_license(self):
        props = SkillProperties(name="skill", description="desc")
        d = props.to_dict()
        assert "license" not in d

    def test_to_dict_excludes_none_compatibility(self):
        props = SkillProperties(name="skill", description="desc")
        d = props.to_dict()
        assert "compatibility" not in d

    def test_to_dict_excludes_none_allowed_tools(self):
        props = SkillProperties(name="skill", description="desc")
        d = props.to_dict()
        assert "allowed-tools" not in d

    def test_to_dict_excludes_empty_metadata(self):
        props = SkillProperties(name="skill", description="desc")
        d = props.to_dict()
        assert "metadata" not in d

    def test_to_dict_includes_license_when_set(self):
        props = SkillProperties(name="skill", description="desc", license="Apache-2.0")
        d = props.to_dict()
        assert d["license"] == "Apache-2.0"

    def test_to_dict_includes_metadata_when_set(self):
        props = SkillProperties(
            name="skill", description="desc", metadata={"author": "Alice"}
        )
        d = props.to_dict()
        assert d["metadata"] == {"author": "Alice"}

    def test_to_dict_uses_kebab_case_for_allowed_tools(self):
        props = SkillProperties(
            name="skill", description="desc", allowed_tools="bash"
        )
        d = props.to_dict()
        assert "allowed-tools" in d


# ---------------------------------------------------------------------------
# Skill Pydantic model tests
# ---------------------------------------------------------------------------


class TestSkillModel:
    """Tests for Skill Pydantic BaseModel."""

    def _make_properties(self) -> SkillProperties:
        return SkillProperties(name="test-skill", description="A test skill")

    def test_basic_construction(self):
        props = self._make_properties()
        skill = Skill(
            properties=props,
            skill_md_path="/path/to/SKILL.md",
            skill_md_content="---\nname: test-skill\n---\nContent",
            source=SkillSource.BUILDIN,
            source_url="https://github.com/example/skill",
        )
        assert skill.properties.name == "test-skill"
        assert skill.skill_md_path == "/path/to/SKILL.md"

    def test_default_source_is_builtin(self):
        props = self._make_properties()
        skill = Skill(
            properties=props,
            skill_md_path="/path/SKILL.md",
            skill_md_content="content",
            source_url="https://example.com",
        )
        assert skill.source == SkillSource.BUILDIN

    def test_source_url_required(self):
        from pydantic import ValidationError

        props = self._make_properties()
        with pytest.raises(ValidationError):
            Skill(
                properties=props,
                skill_md_path="/path/SKILL.md",
                skill_md_content="content",
            )

    def test_git_source(self):
        props = self._make_properties()
        skill = Skill(
            properties=props,
            skill_md_path="/path/SKILL.md",
            skill_md_content="content",
            source=SkillSource.GIT,
            source_url="https://github.com/user/skill-repo",
        )
        assert skill.source == SkillSource.GIT


# ---------------------------------------------------------------------------
# SkillCreator abstract base class tests
# ---------------------------------------------------------------------------


class TestSkillCreatorAbstract:
    """Tests for SkillCreator abstract base class."""

    def test_cannot_instantiate_directly(self):
        with pytest.raises(TypeError):
            SkillCreator()  # type: ignore

    def test_concrete_subclass_must_implement_create_skill_tool(self):
        class IncompleteCreator(SkillCreator):
            pass

        with pytest.raises(TypeError):
            IncompleteCreator()

    def test_concrete_subclass_can_be_instantiated(self):
        class MockSkillCreator(SkillCreator):
            async def create_skill_tool(self):
                return None

        creator = MockSkillCreator()
        assert isinstance(creator, SkillCreator)

    @pytest.mark.asyncio
    async def test_concrete_subclass_returns_none(self):
        class MockSkillCreator(SkillCreator):
            async def create_skill_tool(self):
                return None

        creator = MockSkillCreator()
        result = await creator.create_skill_tool()
        assert result is None

    @pytest.mark.asyncio
    async def test_concrete_subclass_with_implementation(self):
        from types import SimpleNamespace

        fake_tool = SimpleNamespace(name="skill-tool")

        class ConcreteCreator(SkillCreator):
            async def create_skill_tool(self):
                return fake_tool

        creator = ConcreteCreator()
        result = await creator.create_skill_tool()
        assert result is fake_tool


# ---------------------------------------------------------------------------
# Validator: _validate_name tests
# ---------------------------------------------------------------------------


class TestValidateName:
    """Tests for _validate_name()."""

    def _make_skill_dir(self, name: str) -> Path:
        return Path(f"/skills/{name}")

    def test_valid_name(self):
        errors = _validate_name("my-skill", self._make_skill_dir("my-skill"))
        assert errors == []

    def test_name_too_long(self):
        long_name = "a" * (MAX_SKILL_NAME_LENGTH + 1)
        errors = _validate_name(long_name, self._make_skill_dir(long_name))
        assert any("exceeds" in e for e in errors)

    def test_uppercase_name_fails(self):
        errors = _validate_name("My-Skill", self._make_skill_dir("My-Skill"))
        assert any("lowercase" in e for e in errors)

    def test_name_starting_with_hyphen_fails(self):
        errors = _validate_name("-bad-name", self._make_skill_dir("-bad-name"))
        assert any("start" in e or "end" in e or "hyphen" in e for e in errors)

    def test_name_ending_with_hyphen_fails(self):
        errors = _validate_name("bad-name-", self._make_skill_dir("bad-name-"))
        assert any("end" in e or "hyphen" in e for e in errors)

    def test_consecutive_hyphens_fail(self):
        errors = _validate_name("bad--name", self._make_skill_dir("bad--name"))
        assert any("consecutive" in e for e in errors)

    def test_empty_name_fails(self):
        errors = _validate_name("", Path("/skills/x"))
        assert len(errors) > 0

    def test_directory_mismatch_fails(self):
        errors = _validate_name("my-skill", Path("/skills/other-name"))
        assert any("must match" in e or "Directory" in e for e in errors)

    def test_directory_match_passes(self):
        errors = _validate_name("my-skill", Path("/skills/my-skill"))
        assert errors == []

    def test_name_with_special_chars_fails(self):
        errors = _validate_name("my_skill!", self._make_skill_dir("my_skill!"))
        # underscore is not in valid chars set (only letters, digits, hyphens)
        assert len(errors) > 0

    def test_alphanumeric_only_valid(self):
        errors = _validate_name("myskill123", self._make_skill_dir("myskill123"))
        assert errors == []


# ---------------------------------------------------------------------------
# Validator: _validate_description tests
# ---------------------------------------------------------------------------


class TestValidateDescription:
    """Tests for _validate_description()."""

    def test_valid_description(self):
        errors = _validate_description("A helpful skill that does things")
        assert errors == []

    def test_empty_description_fails(self):
        errors = _validate_description("")
        assert len(errors) > 0

    def test_whitespace_only_fails(self):
        errors = _validate_description("   ")
        assert len(errors) > 0

    def test_description_too_long(self):
        long_desc = "a" * (MAX_DESCRIPTION_LENGTH + 1)
        errors = _validate_description(long_desc)
        assert any("exceeds" in e for e in errors)

    def test_description_at_max_length(self):
        max_desc = "a" * MAX_DESCRIPTION_LENGTH
        errors = _validate_description(max_desc)
        assert errors == []

    def test_non_string_fails(self):
        errors = _validate_description(None)  # type: ignore
        assert len(errors) > 0


# ---------------------------------------------------------------------------
# Validator: _validate_compatibility tests
# ---------------------------------------------------------------------------


class TestValidateCompatibility:
    """Tests for _validate_compatibility()."""

    def test_valid_compatibility(self):
        errors = _validate_compatibility(">=1.0")
        assert errors == []

    def test_empty_string_valid(self):
        errors = _validate_compatibility("")
        assert errors == []

    def test_non_string_fails(self):
        errors = _validate_compatibility(123)  # type: ignore
        assert len(errors) > 0

    def test_too_long_fails(self):
        long_compat = "a" * (MAX_COMPATIBILITY_LENGTH + 1)
        errors = _validate_compatibility(long_compat)
        assert any("exceeds" in e for e in errors)


# ---------------------------------------------------------------------------
# Validator: _validate_metadata_fields tests
# ---------------------------------------------------------------------------


class TestValidateMetadataFields:
    """Tests for _validate_metadata_fields()."""

    def test_valid_fields_only(self):
        metadata = {"name": "skill", "description": "desc", "license": "MIT"}
        errors = _validate_metadata_fields(metadata)
        assert errors == []

    def test_extra_field_fails(self):
        metadata = {"name": "skill", "description": "desc", "unknown_field": "value"}
        errors = _validate_metadata_fields(metadata)
        assert any("Unexpected" in e for e in errors)

    def test_all_allowed_fields_valid(self):
        metadata = {
            "name": "s",
            "description": "d",
            "license": "MIT",
            "allowed-tools": "bash",
            "metadata": {},
            "compatibility": ">=1",
        }
        errors = _validate_metadata_fields(metadata)
        assert errors == []

    def test_empty_metadata_valid(self):
        errors = _validate_metadata_fields({})
        assert errors == []


# ---------------------------------------------------------------------------
# Validator: validate_metadata tests
# ---------------------------------------------------------------------------


class TestValidateMetadata:
    """Tests for validate_metadata()."""

    def test_valid_minimal_metadata(self):
        metadata = {"name": "my-skill", "description": "A skill"}
        errors = validate_metadata(metadata, skill_dir=Path("/skills/my-skill"))
        assert errors == []

    def test_missing_name_fails(self):
        metadata = {"description": "A skill"}
        errors = validate_metadata(metadata)
        assert any("name" in e for e in errors)

    def test_missing_description_fails(self):
        metadata = {"name": "my-skill"}
        errors = validate_metadata(metadata, skill_dir=Path("/skills/my-skill"))
        assert any("description" in e for e in errors)

    def test_both_required_fields_missing(self):
        errors = validate_metadata({})
        assert len(errors) >= 2

    def test_extra_field_produces_error(self):
        metadata = {
            "name": "my-skill",
            "description": "desc",
            "extra_field": "not-allowed",
        }
        errors = validate_metadata(metadata, skill_dir=Path("/skills/my-skill"))
        assert len(errors) > 0

    def test_with_optional_compatibility(self):
        metadata = {
            "name": "my-skill",
            "description": "A skill",
            "compatibility": ">=2.0",
        }
        errors = validate_metadata(metadata, skill_dir=Path("/skills/my-skill"))
        assert errors == []

    def test_no_skill_dir_skips_dir_check(self):
        metadata = {"name": "my-skill", "description": "A skill"}
        errors = validate_metadata(metadata, skill_dir=None)
        assert errors == []
