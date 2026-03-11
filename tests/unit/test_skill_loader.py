"""
Unit tests for skills/skill_loader.py.

Reads real skill .md files — no OpenAI API calls.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from skills.skill_loader import Skill, SkillLoader, _parse_skill_file


# ---------------------------------------------------------------------------
# _parse_skill_file (low-level parser)
# ---------------------------------------------------------------------------

class TestParseSkillFile:
    def test_parses_valid_file(self, tmp_path):
        md = tmp_path / "test_skill.md"
        md.write_text(textwrap.dedent("""\
            ---
            name: TestSkill
            display_name: Test Skill
            model: gpt-4o
            tools:
              - tool_a
              - tool_b
            ---

            # Instructions

            Do something useful.
        """), encoding="utf-8")
        skill = _parse_skill_file(md)
        assert skill.name == "TestSkill"
        assert skill.display_name == "Test Skill"
        assert skill.model == "gpt-4o"
        assert skill.tool_names == ["tool_a", "tool_b"]
        assert "Do something useful" in skill.instructions

    def test_uses_default_model_when_omitted(self, tmp_path):
        md = tmp_path / "no_model.md"
        md.write_text(textwrap.dedent("""\
            ---
            name: NoModel
            ---

            Instructions here.
        """), encoding="utf-8")
        skill = _parse_skill_file(md)
        assert skill.model == "gpt-4o"

    def test_empty_tools_list_when_omitted(self, tmp_path):
        md = tmp_path / "no_tools.md"
        md.write_text(textwrap.dedent("""\
            ---
            name: NoTools
            ---

            Instructions.
        """), encoding="utf-8")
        skill = _parse_skill_file(md)
        assert skill.tool_names == []

    def test_raises_on_missing_frontmatter(self, tmp_path):
        md = tmp_path / "no_fm.md"
        md.write_text("Just plain markdown with no frontmatter.", encoding="utf-8")
        with pytest.raises(ValueError, match="missing a valid YAML frontmatter"):
            _parse_skill_file(md)

    def test_raises_when_name_missing(self, tmp_path):
        md = tmp_path / "no_name.md"
        md.write_text(textwrap.dedent("""\
            ---
            model: gpt-4o
            ---

            Instructions.
        """), encoding="utf-8")
        with pytest.raises(ValueError, match="missing required key 'name'"):
            _parse_skill_file(md)

    def test_display_name_falls_back_to_name(self, tmp_path):
        md = tmp_path / "fallback.md"
        md.write_text(textwrap.dedent("""\
            ---
            name: FallbackSkill
            ---

            Instructions.
        """), encoding="utf-8")
        skill = _parse_skill_file(md)
        assert skill.display_name == "FallbackSkill"

    def test_source_file_is_set(self, tmp_path):
        md = tmp_path / "sourced.md"
        md.write_text(textwrap.dedent("""\
            ---
            name: Sourced
            ---

            Instructions.
        """), encoding="utf-8")
        skill = _parse_skill_file(md)
        assert skill.source_file == md


# ---------------------------------------------------------------------------
# SkillLoader — loading real skill files
# ---------------------------------------------------------------------------

class TestSkillLoaderRealFiles:
    """These tests load the actual skill .md files from skills/ directory."""

    def setup_method(self):
        SkillLoader.invalidate_cache()

    def test_load_new_volume_agent(self):
        skill = SkillLoader.load("new_volume_agent")
        assert skill.name is not None
        assert len(skill.tool_names) > 0
        assert len(skill.instructions) > 50

    def test_load_risk_agent(self):
        skill = SkillLoader.load("risk_agent")
        assert skill.name is not None
        assert len(skill.tool_names) > 0

    def test_load_allocation_agent(self):
        skill = SkillLoader.load("allocation_agent")
        assert skill.name is not None
        assert len(skill.tool_names) > 0

    def test_load_mbs_decomposition_agent(self):
        skill = SkillLoader.load("mbs_decomposition_agent")
        assert skill.name is not None
        assert len(skill.tool_names) > 0

    def test_all_skills_have_non_empty_instructions(self):
        skills = SkillLoader.load_all()
        for name, skill in skills.items():
            assert skill.instructions.strip() != "", f"Empty instructions in {name}"

    def test_list_available_returns_all_four_agents(self):
        available = SkillLoader.list_available()
        expected = {"new_volume_agent", "risk_agent", "allocation_agent", "mbs_decomposition_agent"}
        assert expected.issubset(set(available))

    def test_skill_is_cached_on_second_load(self):
        skill_1 = SkillLoader.load("new_volume_agent")
        skill_2 = SkillLoader.load("new_volume_agent")
        assert skill_1 is skill_2

    def test_cache_cleared_by_invalidate(self):
        skill_1 = SkillLoader.load("risk_agent")
        SkillLoader.invalidate_cache()
        skill_2 = SkillLoader.load("risk_agent")
        # After cache clear, a new object is returned
        assert skill_1 is not skill_2

    def test_raises_for_nonexistent_skill(self):
        with pytest.raises(FileNotFoundError, match="No skill found"):
            SkillLoader.load("does_not_exist")


# ---------------------------------------------------------------------------
# SkillLoader — synthetic temp directory
# ---------------------------------------------------------------------------

class TestSkillLoaderCustomDir:
    def test_load_from_custom_directory(self, tmp_path):
        md = tmp_path / "custom_agent.md"
        md.write_text(textwrap.dedent("""\
            ---
            name: CustomAgent
            model: gpt-4o-mini
            tools: []
            ---

            Custom instructions.
        """), encoding="utf-8")
        skill = SkillLoader.load("custom_agent", skills_dir=tmp_path)
        assert skill.name == "CustomAgent"
        assert skill.model == "gpt-4o-mini"

    def test_load_all_from_custom_directory(self, tmp_path):
        for i in range(3):
            md = tmp_path / f"agent_{i}.md"
            md.write_text(textwrap.dedent(f"""\
                ---
                name: Agent{i}
                ---

                Instructions for agent {i}.
            """), encoding="utf-8")
        skills = SkillLoader.load_all(skills_dir=tmp_path)
        assert len(skills) == 3

    def test_non_skill_md_files_skipped(self, tmp_path):
        """Markdown files without frontmatter should be silently skipped."""
        (tmp_path / "README.md").write_text("# Just a readme", encoding="utf-8")
        md = tmp_path / "real_agent.md"
        md.write_text(textwrap.dedent("""\
            ---
            name: RealAgent
            ---

            Real instructions.
        """), encoding="utf-8")
        skills = SkillLoader.load_all(skills_dir=tmp_path)
        assert "real_agent" in skills
        assert "README" not in skills
