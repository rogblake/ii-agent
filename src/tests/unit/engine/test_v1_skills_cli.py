"""Unit tests for engine/v1/skills/skills_ref/cli.py.

Tests CLI commands using Click's CliRunner for isolated invocation.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from ii_agent.engine.v1.skills.skills_ref.cli import (
    _is_skill_md_file,
    main,
    read_properties_cmd,
    to_prompt_cmd,
    validate_cmd,
)
from ii_agent.engine.v1.skills.skills_ref.errors import SkillError
from ii_agent.engine.v1.skills.skills_ref.models import SkillProperties


# ---------------------------------------------------------------------------
# _is_skill_md_file
# ---------------------------------------------------------------------------


class TestIsSkillMdFile:
    def test_returns_true_for_skill_md(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# skill")
        assert _is_skill_md_file(skill_md) is True

    def test_returns_true_for_lowercase_skill_md(self, tmp_path):
        skill_md = tmp_path / "skill.md"
        skill_md.write_text("# skill")
        assert _is_skill_md_file(skill_md) is True

    def test_returns_false_for_directory(self, tmp_path):
        assert _is_skill_md_file(tmp_path) is False

    def test_returns_false_for_other_file(self, tmp_path):
        other = tmp_path / "README.md"
        other.write_text("hi")
        assert _is_skill_md_file(other) is False

    def test_returns_false_for_nonexistent_path(self, tmp_path):
        nonexistent = tmp_path / "SKILL.md"
        # File does not exist
        assert _is_skill_md_file(nonexistent) is False


# ---------------------------------------------------------------------------
# validate_cmd
# ---------------------------------------------------------------------------


class TestValidateCmd:
    def test_valid_skill_prints_valid_message(self, tmp_path):
        runner = CliRunner()

        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.validate", return_value=[]
        ):
            result = runner.invoke(validate_cmd, [str(tmp_path)])

        assert result.exit_code == 0
        assert "Valid skill" in result.output

    def test_validation_errors_print_to_stderr_and_exit_1(self, tmp_path):
        runner = CliRunner()

        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.validate",
            return_value=["Missing required field: name", "Name must be lowercase"],
        ):
            result = runner.invoke(validate_cmd, [str(tmp_path)])

        assert result.exit_code == 1

    def test_skill_md_path_resolves_to_parent(self, tmp_path):
        """When a SKILL.md file is passed, the parent directory is used."""
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("dummy")

        validated_paths = []

        def capturing_validate(path):
            validated_paths.append(path)
            return []

        runner = CliRunner()
        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.validate",
            side_effect=capturing_validate,
        ):
            result = runner.invoke(validate_cmd, [str(skill_md)])

        assert result.exit_code == 0
        # The CLI should have resolved to the parent directory
        assert validated_paths[0] == tmp_path

    def test_multiple_validation_errors_all_printed(self, tmp_path):
        runner = CliRunner()
        errors = ["error1", "error2", "error3"]

        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.validate", return_value=errors
        ):
            result = runner.invoke(validate_cmd, [str(tmp_path)])

        # All errors should be present in the combined output+stderr
        for err in errors:
            assert err in (result.output + (result.stderr if hasattr(result, "stderr") else ""))


# ---------------------------------------------------------------------------
# read_properties_cmd
# ---------------------------------------------------------------------------


class TestReadPropertiesCmd:
    def test_outputs_json_on_success(self, tmp_path):
        runner = CliRunner()

        mock_props = SkillProperties(name="my-skill", description="Does things")

        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.read_properties",
            return_value=mock_props,
        ):
            result = runner.invoke(read_properties_cmd, [str(tmp_path)])

        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["name"] == "my-skill"
        assert data["description"] == "Does things"

    def test_skill_error_prints_to_stderr_and_exits_1(self, tmp_path):
        runner = CliRunner()

        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.read_properties",
            side_effect=SkillError("SKILL.md not found"),
        ):
            result = runner.invoke(read_properties_cmd, [str(tmp_path)])

        assert result.exit_code == 1

    def test_skill_md_path_resolves_to_parent(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("dummy")

        captured_paths = []

        def capturing_read(path):
            captured_paths.append(path)
            return SkillProperties(name="x", description="y")

        runner = CliRunner()
        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.read_properties",
            side_effect=capturing_read,
        ):
            result = runner.invoke(read_properties_cmd, [str(skill_md)])

        assert result.exit_code == 0
        assert captured_paths[0] == tmp_path

    def test_json_output_indented(self, tmp_path):
        runner = CliRunner()

        mock_props = SkillProperties(
            name="indented-skill",
            description="Has nice output",
            license="MIT",
        )

        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.read_properties",
            return_value=mock_props,
        ):
            result = runner.invoke(read_properties_cmd, [str(tmp_path)])

        # Should be valid JSON and indented (i.e., has newlines)
        assert "\n" in result.output
        data = json.loads(result.output)
        assert data.get("license") == "MIT"


# ---------------------------------------------------------------------------
# to_prompt_cmd
# ---------------------------------------------------------------------------


class TestToPromptCmd:
    def test_outputs_xml_on_success(self, tmp_path):
        runner = CliRunner()

        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.to_prompt",
            return_value="<available_skills>\n</available_skills>",
        ):
            result = runner.invoke(to_prompt_cmd, [str(tmp_path)])

        assert result.exit_code == 0
        assert "<available_skills>" in result.output

    def test_skill_error_prints_and_exits_1(self, tmp_path):
        runner = CliRunner()

        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.to_prompt",
            side_effect=SkillError("cannot read skill"),
        ):
            result = runner.invoke(to_prompt_cmd, [str(tmp_path)])

        assert result.exit_code == 1

    def test_skill_md_files_resolved_to_parent(self, tmp_path):
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("dummy")

        captured_paths = []

        def capturing_prompt(paths):
            captured_paths.extend(paths)
            return "<available_skills>\n</available_skills>"

        runner = CliRunner()
        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.to_prompt",
            side_effect=capturing_prompt,
        ):
            result = runner.invoke(to_prompt_cmd, [str(skill_md)])

        assert result.exit_code == 0
        assert tmp_path in captured_paths

    def test_multiple_skill_paths_passed(self, tmp_path):
        skill_a = tmp_path / "a"
        skill_a.mkdir()
        skill_b = tmp_path / "b"
        skill_b.mkdir()

        captured_paths = []

        def capturing_prompt(paths):
            captured_paths.extend(paths)
            return "<available_skills>\n</available_skills>"

        runner = CliRunner()
        with patch(
            "ii_agent.engine.v1.skills.skills_ref.cli.to_prompt",
            side_effect=capturing_prompt,
        ):
            result = runner.invoke(to_prompt_cmd, [str(skill_a), str(skill_b)])

        assert result.exit_code == 0
        assert len(captured_paths) == 2


# ---------------------------------------------------------------------------
# Main CLI group
# ---------------------------------------------------------------------------


class TestMainCliGroup:
    def test_help_text_present(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "Agent Skills" in result.output

    def test_subcommands_listed_in_help(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "validate" in result.output
        assert "read-properties" in result.output
        assert "to-prompt" in result.output
