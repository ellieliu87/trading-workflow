"""
Integration tests — live OpenAI API calls.

Each test runs a real agent against a populated WorkflowState and asserts that:
  1. The agent completes without error.
  2. The agent invoked the expected tools (state side-effects are visible).
  3. The agent's text output is non-empty and plausibly on-topic.

These tests are skipped automatically when OPENAI_API_KEY is not set.
See tests/integration/conftest.py for the skip logic.
"""

from __future__ import annotations

import pytest
from agents import Runner

from models.workflow_state import RiskAppetite, WorkflowPhase
from skills.skill_loader import SkillLoader


# ---------------------------------------------------------------------------
# NewVolumeAgent
# ---------------------------------------------------------------------------

class TestNewVolumeAgentLive:
    async def test_agent_completes(self, fresh_state):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("new_volume_agent").build()
        result = await Runner.run(
            agent,
            "Calculate the full 12-month and 10-year new volume schedule "
            "and provide a one-page summary.",
            context=fresh_state,
        )
        assert result.final_output is not None
        assert len(result.final_output) > 50

    async def test_agent_populates_12m_volume(self, fresh_state):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("new_volume_agent").build()
        await Runner.run(
            agent,
            "Calculate the full 12-month and 10-year new volume schedule.",
            context=fresh_state,
        )
        # compute_new_volume_schedule tool should have set this
        assert fresh_state.next_12m_new_volume_mm > 0

    async def test_agent_populates_10yr_volume(self, fresh_state):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("new_volume_agent").build()
        await Runner.run(
            agent,
            "Calculate the full 12-month and 10-year new volume schedule.",
            context=fresh_state,
        )
        assert fresh_state.total_10yr_new_volume_mm > fresh_state.next_12m_new_volume_mm

    async def test_output_mentions_dollar_amounts(self, fresh_state):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("new_volume_agent").build()
        result = await Runner.run(
            agent,
            "Calculate the full 12-month and 10-year new volume schedule "
            "and provide a one-page summary.",
            context=fresh_state,
        )
        # Agent should mention dollar amounts (MM or $)
        assert any(tok in result.final_output for tok in ["$", "MM", "mm", "million", "billion"])


# ---------------------------------------------------------------------------
# RiskAgent
# ---------------------------------------------------------------------------

class TestRiskAgentLive:
    async def test_agent_completes(self, fresh_state):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("risk_agent").build()
        result = await Runner.run(
            agent,
            "Assess the current portfolio risk and establish risk guardrails "
            "for the upcoming purchase program.",
            context=fresh_state,
        )
        assert result.final_output is not None
        assert len(result.final_output) > 50

    async def test_agent_populates_risk_constraints(self, fresh_state):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("risk_agent").build()
        await Runner.run(
            agent,
            "Assess portfolio risk and establish guardrails.",
            context=fresh_state,
        )
        assert fresh_state.risk_constraints is not None

    async def test_risk_constraints_are_valid(self, fresh_state):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("risk_agent").build()
        await Runner.run(
            agent,
            "Assess portfolio risk and establish guardrails.",
            context=fresh_state,
        )
        rc = fresh_state.risk_constraints
        assert rc.duration_min < rc.duration_max
        assert rc.duration_min > 0
        assert 0 < rc.liquidity_score_min <= 10

    async def test_output_mentions_duration(self, fresh_state):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("risk_agent").build()
        result = await Runner.run(
            agent,
            "Assess portfolio risk and establish guardrails.",
            context=fresh_state,
        )
        assert "duration" in result.final_output.lower()


# ---------------------------------------------------------------------------
# AllocationAgent
# ---------------------------------------------------------------------------

class TestAllocationAgentLive:
    @pytest.fixture()
    async def state_after_risk(self, fresh_state):
        """Run RiskAgent first so risk_constraints are available."""
        SkillLoader.invalidate_cache()
        risk_agent = SkillLoader.load("risk_agent").build()
        await Runner.run(
            risk_agent,
            "Assess portfolio risk and establish guardrails.",
            context=fresh_state,
        )
        fresh_state.next_12m_new_volume_mm = 5_400.0
        return fresh_state

    async def test_agent_completes(self, state_after_risk):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("allocation_agent").build()
        result = await Runner.run(
            agent,
            "Generate three allocation scenarios (conservative, moderate, aggressive) "
            "for the upcoming purchase program and explain the trade-offs.",
            context=state_after_risk,
        )
        assert result.final_output is not None
        assert len(result.final_output) > 50

    async def test_agent_generates_three_scenarios(self, state_after_risk):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("allocation_agent").build()
        await Runner.run(
            agent,
            "Generate three allocation scenarios.",
            context=state_after_risk,
        )
        assert len(state_after_risk.allocation_scenarios) == 3

    async def test_scenario_weights_sum_to_100(self, state_after_risk):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("allocation_agent").build()
        await Runner.run(
            agent,
            "Generate three allocation scenarios.",
            context=state_after_risk,
        )
        for s in state_after_risk.allocation_scenarios:
            total = s.mbs_pct + s.cmbs_pct + s.treasury_pct
            assert abs(total - 100.0) < 0.1, f"Weights off for {s.scenario_id}: {total}"

    async def test_output_mentions_all_three_scenarios(self, state_after_risk):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("allocation_agent").build()
        result = await Runner.run(
            agent,
            "Generate three allocation scenarios and explain trade-offs.",
            context=state_after_risk,
        )
        output_lower = result.final_output.lower()
        assert "conservative" in output_lower
        assert "moderate" in output_lower
        assert "aggressive" in output_lower


# ---------------------------------------------------------------------------
# MBSDecompositionAgent
# ---------------------------------------------------------------------------

class TestMBSDecompositionAgentLive:
    @pytest.fixture()
    async def state_with_scenario(self, fresh_state):
        """Run Risk + Allocation agents so a scenario is selected."""
        SkillLoader.invalidate_cache()

        risk_agent = SkillLoader.load("risk_agent").build()
        await Runner.run(
            risk_agent, "Assess portfolio risk.", context=fresh_state
        )
        fresh_state.next_12m_new_volume_mm = 5_400.0

        alloc_agent = SkillLoader.load("allocation_agent").build()
        await Runner.run(
            alloc_agent, "Generate allocation scenarios.", context=fresh_state
        )
        # Manually select moderate scenario (no gate in integration test)
        moderate = next(
            s for s in fresh_state.allocation_scenarios if s.scenario_id == "moderate"
        )
        fresh_state.selected_scenario = moderate
        return fresh_state

    async def test_agent_completes(self, state_with_scenario):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("mbs_decomposition_agent").build()
        result = await Runner.run(
            agent,
            "Break down the MBS allocation into agency sub-buckets and "
            "compile the final purchase schedule.",
            context=state_with_scenario,
        )
        assert result.final_output is not None
        assert len(result.final_output) > 50

    async def test_agent_populates_mbs_breakdown(self, state_with_scenario):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("mbs_decomposition_agent").build()
        await Runner.run(
            agent,
            "Break down the MBS allocation into sub-buckets and build the purchase schedule.",
            context=state_with_scenario,
        )
        assert state_with_scenario.mbs_breakdown is not None

    async def test_mbs_breakdown_pcts_sum_to_100(self, state_with_scenario):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("mbs_decomposition_agent").build()
        await Runner.run(
            agent,
            "Break down the MBS allocation into sub-buckets and build the purchase schedule.",
            context=state_with_scenario,
        )
        bd = state_with_scenario.mbs_breakdown
        total = (
            bd.fnma_fixed_30yr_pct + bd.fhlmc_fixed_30yr_pct + bd.gnma_fixed_30yr_pct
            + bd.fnma_fixed_15yr_pct + bd.fhlmc_fixed_15yr_pct + bd.arm_pct
        )
        assert abs(total - 100.0) < 0.1

    async def test_agent_builds_purchase_schedule(self, state_with_scenario):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("mbs_decomposition_agent").build()
        await Runner.run(
            agent,
            "Break down MBS and compile the final purchase schedule.",
            context=state_with_scenario,
        )
        assert len(state_with_scenario.purchase_schedule) > 0

    async def test_purchase_schedule_covers_all_asset_classes(self, state_with_scenario):
        SkillLoader.invalidate_cache()
        agent = SkillLoader.load("mbs_decomposition_agent").build()
        await Runner.run(
            agent,
            "Break down MBS and compile the final purchase schedule.",
            context=state_with_scenario,
        )
        types = {item.product_type for item in state_with_scenario.purchase_schedule}
        assert "MBS" in types
        assert "CMBS" in types
        assert "TREASURY" in types
