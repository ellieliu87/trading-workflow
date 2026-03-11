"""
Unit tests for tools/allocation_tools.py.

No OpenAI API calls.  Tools are invoked via on_invoke_tool().
"""

from __future__ import annotations

import json

import pytest

from tests.conftest import make_ctx
from tools.allocation_tools import (
    build_purchase_schedule,
    decompose_mbs_allocation,
    generate_allocation_scenarios,
    select_allocation_scenario,
)


# ---------------------------------------------------------------------------
# generate_allocation_scenarios
# ---------------------------------------------------------------------------

class TestGenerateAllocationScenarios:
    async def test_returns_valid_json(self, state_with_risk):
        result = json.loads(
            await generate_allocation_scenarios.on_invoke_tool(make_ctx(state_with_risk), "{}")
        )
        assert isinstance(result, list)

    async def test_generates_three_scenarios(self, state_with_risk):
        result = json.loads(
            await generate_allocation_scenarios.on_invoke_tool(make_ctx(state_with_risk), "{}")
        )
        assert len(result) == 3

    async def test_scenario_ids_are_correct(self, state_with_risk):
        result = json.loads(
            await generate_allocation_scenarios.on_invoke_tool(make_ctx(state_with_risk), "{}")
        )
        ids = {s["scenario_id"] for s in result}
        assert ids == {"conservative", "moderate", "aggressive"}

    async def test_each_scenario_has_required_fields(self, state_with_risk):
        result = json.loads(
            await generate_allocation_scenarios.on_invoke_tool(make_ctx(state_with_risk), "{}")
        )
        required = {"scenario_id", "label", "mbs_pct", "cmbs_pct", "treasury_pct",
                    "mbs_mm", "cmbs_mm", "treasury_mm", "total_new_volume_mm",
                    "projected_duration", "projected_liquidity_score",
                    "projected_yield_pct", "rationale"}
        for s in result:
            assert required.issubset(s.keys()), f"Missing fields: {required - s.keys()}"

    async def test_weights_sum_to_100(self, state_with_risk):
        result = json.loads(
            await generate_allocation_scenarios.on_invoke_tool(make_ctx(state_with_risk), "{}")
        )
        for s in result:
            total = s["mbs_pct"] + s["cmbs_pct"] + s["treasury_pct"]
            assert abs(total - 100.0) < 0.01, f"Weights don't sum to 100: {total}"

    async def test_dollar_amounts_are_positive(self, state_with_risk):
        result = json.loads(
            await generate_allocation_scenarios.on_invoke_tool(make_ctx(state_with_risk), "{}")
        )
        for s in result:
            assert s["mbs_mm"] > 0
            assert s["total_new_volume_mm"] > 0

    async def test_aggressive_has_higher_yield_than_conservative(self, state_with_risk):
        result = json.loads(
            await generate_allocation_scenarios.on_invoke_tool(make_ctx(state_with_risk), "{}")
        )
        by_id = {s["scenario_id"]: s for s in result}
        assert by_id["aggressive"]["projected_yield_pct"] > by_id["conservative"]["projected_yield_pct"]

    async def test_conservative_has_higher_tsy_pct(self, state_with_risk):
        result = json.loads(
            await generate_allocation_scenarios.on_invoke_tool(make_ctx(state_with_risk), "{}")
        )
        by_id = {s["scenario_id"]: s for s in result}
        assert by_id["conservative"]["treasury_pct"] > by_id["aggressive"]["treasury_pct"]

    async def test_scenarios_stored_on_state(self, state_with_risk):
        await generate_allocation_scenarios.on_invoke_tool(make_ctx(state_with_risk), "{}")
        assert len(state_with_risk.allocation_scenarios) == 3

    async def test_cmbs_clamped_to_risk_constraint(self, state_with_risk):
        """Aggressive CMBS (28%) should be clamped to max_cmbs_pct (30%) from constraints."""
        await generate_allocation_scenarios.on_invoke_tool(make_ctx(state_with_risk), "{}")
        for s in state_with_risk.allocation_scenarios:
            assert s.cmbs_pct <= state_with_risk.risk_constraints.max_cmbs_pct + 0.01


# ---------------------------------------------------------------------------
# select_allocation_scenario
# ---------------------------------------------------------------------------

class TestSelectAllocationScenario:
    async def _setup(self, state):
        """Run generate first so scenarios exist in state."""
        await generate_allocation_scenarios.on_invoke_tool(make_ctx(state), "{}")

    async def test_select_moderate_succeeds(self, state_with_risk):
        await self._setup(state_with_risk)
        result = json.loads(
            await select_allocation_scenario.on_invoke_tool(
                make_ctx(state_with_risk), json.dumps({"scenario_id": "moderate"})
            )
        )
        assert result["status"] == "selected"
        assert result["scenario"]["scenario_id"] == "moderate"

    async def test_selected_scenario_stored_on_state(self, state_with_risk):
        await self._setup(state_with_risk)
        await select_allocation_scenario.on_invoke_tool(
            make_ctx(state_with_risk), json.dumps({"scenario_id": "conservative"})
        )
        assert state_with_risk.selected_scenario is not None
        assert state_with_risk.selected_scenario.scenario_id == "conservative"

    async def test_select_invalid_scenario_returns_error(self, state_with_risk):
        await self._setup(state_with_risk)
        result = json.loads(
            await select_allocation_scenario.on_invoke_tool(
                make_ctx(state_with_risk), json.dumps({"scenario_id": "ultra_aggressive"})
            )
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# decompose_mbs_allocation
# ---------------------------------------------------------------------------

class TestDecomposeMBSAllocation:
    async def test_returns_valid_json(self, state_with_allocation):
        result = json.loads(
            await decompose_mbs_allocation.on_invoke_tool(make_ctx(state_with_allocation), "{}")
        )
        assert isinstance(result, dict)

    async def test_pct_fields_present(self, state_with_allocation):
        result = json.loads(
            await decompose_mbs_allocation.on_invoke_tool(make_ctx(state_with_allocation), "{}")
        )
        assert "fnma_fixed_30yr_pct" in result
        assert "fhlmc_fixed_30yr_pct" in result
        assert "gnma_fixed_30yr_pct" in result
        assert "arm_pct" in result

    async def test_all_pcts_sum_to_100(self, state_with_allocation):
        result = json.loads(
            await decompose_mbs_allocation.on_invoke_tool(make_ctx(state_with_allocation), "{}")
        )
        total = (
            result["fnma_fixed_30yr_pct"]
            + result["fhlmc_fixed_30yr_pct"]
            + result["gnma_fixed_30yr_pct"]
            + result["fnma_fixed_15yr_pct"]
            + result["fhlmc_fixed_15yr_pct"]
            + result["arm_pct"]
        )
        assert abs(total - 100.0) < 0.01, f"MBS pcts don't sum to 100: {total}"

    async def test_dollar_amounts_consistent_with_pcts(self, state_with_allocation):
        result = json.loads(
            await decompose_mbs_allocation.on_invoke_tool(make_ctx(state_with_allocation), "{}")
        )
        mbs_total = state_with_allocation.selected_scenario.mbs_mm
        expected_fnma_mm = round(mbs_total * result["fnma_fixed_30yr_pct"] / 100, 1)
        assert abs(result["fnma_fixed_30yr_mm"] - expected_fnma_mm) < 0.2

    async def test_conservative_has_zero_arm(self, state_with_allocation):
        state_with_allocation.risk_appetite = "conservative"
        result = json.loads(
            await decompose_mbs_allocation.on_invoke_tool(make_ctx(state_with_allocation), "{}")
        )
        assert result["arm_pct"] == 0.0

    async def test_mbs_breakdown_stored_on_state(self, state_with_allocation):
        await decompose_mbs_allocation.on_invoke_tool(make_ctx(state_with_allocation), "{}")
        assert state_with_allocation.mbs_breakdown is not None

    async def test_error_when_no_selected_scenario(self, state_with_risk):
        result = json.loads(
            await decompose_mbs_allocation.on_invoke_tool(make_ctx(state_with_risk), "{}")
        )
        assert "error" in result

    async def test_rationale_is_non_empty_string(self, state_with_allocation):
        result = json.loads(
            await decompose_mbs_allocation.on_invoke_tool(make_ctx(state_with_allocation), "{}")
        )
        assert isinstance(result["rationale"], str)
        assert len(result["rationale"]) > 10


# ---------------------------------------------------------------------------
# build_purchase_schedule
# ---------------------------------------------------------------------------

class TestBuildPurchaseSchedule:
    async def test_returns_valid_json(self, state_with_mbs_breakdown):
        result = json.loads(
            await build_purchase_schedule.on_invoke_tool(make_ctx(state_with_mbs_breakdown), "{}")
        )
        assert isinstance(result, dict)

    async def test_contains_schedule_and_total(self, state_with_mbs_breakdown):
        result = json.loads(
            await build_purchase_schedule.on_invoke_tool(make_ctx(state_with_mbs_breakdown), "{}")
        )
        assert "items" in result
        assert "total_purchase_amount_mm" in result

    async def test_all_items_have_required_fields(self, state_with_mbs_breakdown):
        result = json.loads(
            await build_purchase_schedule.on_invoke_tool(make_ctx(state_with_mbs_breakdown), "{}")
        )
        required = {"product_type", "sub_type", "amount_mm", "target_duration",
                    "target_oas_bps", "priority"}
        for item in result["items"]:
            assert required.issubset(item.keys()), f"Missing fields in: {item}"

    async def test_all_items_have_positive_amounts(self, state_with_mbs_breakdown):
        result = json.loads(
            await build_purchase_schedule.on_invoke_tool(make_ctx(state_with_mbs_breakdown), "{}")
        )
        for item in result["items"]:
            assert item["amount_mm"] > 0, f"Zero amount for {item['sub_type']}"

    async def test_product_types_cover_all_asset_classes(self, state_with_mbs_breakdown):
        result = json.loads(
            await build_purchase_schedule.on_invoke_tool(make_ctx(state_with_mbs_breakdown), "{}")
        )
        types = {item["product_type"] for item in result["items"]}
        assert "MBS" in types
        assert "CMBS" in types
        assert "TREASURY" in types

    async def test_priorities_are_unique(self, state_with_mbs_breakdown):
        result = json.loads(
            await build_purchase_schedule.on_invoke_tool(make_ctx(state_with_mbs_breakdown), "{}")
        )
        priorities = [item["priority"] for item in result["items"]]
        assert len(priorities) == len(set(priorities))

    async def test_total_is_sum_of_items(self, state_with_mbs_breakdown):
        result = json.loads(
            await build_purchase_schedule.on_invoke_tool(make_ctx(state_with_mbs_breakdown), "{}")
        )
        computed_total = sum(item["amount_mm"] for item in result["items"])
        assert abs(result["total_purchase_amount_mm"] - computed_total) < 0.1

    async def test_purchase_schedule_stored_on_state(self, state_with_mbs_breakdown):
        await build_purchase_schedule.on_invoke_tool(make_ctx(state_with_mbs_breakdown), "{}")
        assert len(state_with_mbs_breakdown.purchase_schedule) > 0

    async def test_error_when_missing_breakdown(self, state_with_allocation):
        """Breakdown not set — should return error."""
        result = json.loads(
            await build_purchase_schedule.on_invoke_tool(make_ctx(state_with_allocation), "{}")
        )
        assert "error" in result

    async def test_error_when_missing_scenario(self, bare_state):
        result = json.loads(
            await build_purchase_schedule.on_invoke_tool(make_ctx(bare_state), "{}")
        )
        assert "error" in result
