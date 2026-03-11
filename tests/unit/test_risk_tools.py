"""
Unit tests for tools/risk_tools.py.

No OpenAI API calls.  Tools are invoked via on_invoke_tool().
"""

from __future__ import annotations

import json

import pytest

from models.workflow_state import RiskConstraints
from tests.conftest import make_ctx
from tools.risk_tools import (
    assess_portfolio_risk,
    estimate_duration_impact,
    get_risk_constraints_summary,
)


# ---------------------------------------------------------------------------
# assess_portfolio_risk
# ---------------------------------------------------------------------------

class TestAssessPortfolioRisk:
    async def test_returns_valid_json(self, state_with_pool_summary):
        result = json.loads(
            await assess_portfolio_risk.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        )
        assert isinstance(result, dict)

    async def test_contains_required_top_level_keys(self, state_with_pool_summary):
        result = json.loads(
            await assess_portfolio_risk.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        )
        assert "current_portfolio" in result
        assert "risk_constraints" in result
        assert "flags" in result
        assert "recommendation" in result

    async def test_current_portfolio_has_duration(self, state_with_pool_summary):
        result = json.loads(
            await assess_portfolio_risk.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        )
        assert "duration_years" in result["current_portfolio"]
        assert result["current_portfolio"]["duration_years"] > 0

    async def test_current_portfolio_has_liquidity_score(self, state_with_pool_summary):
        result = json.loads(
            await assess_portfolio_risk.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        )
        assert "liquidity_score" in result["current_portfolio"]
        assert 0 < result["current_portfolio"]["liquidity_score"] <= 10

    async def test_risk_constraints_populated_on_state(self, state_with_pool_summary):
        await assess_portfolio_risk.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        assert state_with_pool_summary.risk_constraints is not None

    async def test_duration_min_less_than_max(self, state_with_pool_summary):
        await assess_portfolio_risk.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        rc = state_with_pool_summary.risk_constraints
        assert rc.duration_min < rc.duration_max

    async def test_flags_is_list(self, state_with_pool_summary):
        result = json.loads(
            await assess_portfolio_risk.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        )
        assert isinstance(result["flags"], list)

    async def test_concentration_sums_to_100(self, state_with_pool_summary):
        result = json.loads(
            await assess_portfolio_risk.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        )
        total = sum(result["current_portfolio"]["concentration_pct"].values())
        assert abs(total - 100.0) < 0.5  # allow small rounding delta

    async def test_error_when_no_pool_summary(self, bare_state):
        result = json.loads(
            await assess_portfolio_risk.on_invoke_tool(make_ctx(bare_state), "{}")
        )
        assert "error" in result

    async def test_risk_report_stored_on_state(self, state_with_pool_summary):
        await assess_portfolio_risk.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        assert state_with_pool_summary.risk_report != ""


# ---------------------------------------------------------------------------
# estimate_duration_impact
# ---------------------------------------------------------------------------

class TestEstimateDurationImpact:
    async def _call(self, state, mbs_pct, cmbs_pct, treasury_pct, new_volume_mm=500.0):
        args = json.dumps({
            "mbs_pct": mbs_pct,
            "cmbs_pct": cmbs_pct,
            "treasury_pct": treasury_pct,
            "new_volume_mm": new_volume_mm,
        })
        return json.loads(
            await estimate_duration_impact.on_invoke_tool(make_ctx(state), args)
        )

    async def test_returns_valid_json(self, state_with_risk):
        result = await self._call(state_with_risk, 60, 22, 18)
        assert isinstance(result, dict)

    async def test_contains_duration_and_liquidity(self, state_with_risk):
        result = await self._call(state_with_risk, 60, 22, 18)
        assert "new_purchase_duration" in result
        assert "projected_portfolio_duration" in result
        assert "projected_liquidity_score" in result

    async def test_duration_is_positive(self, state_with_risk):
        result = await self._call(state_with_risk, 60, 22, 18)
        assert result["projected_portfolio_duration"] > 0

    async def test_tsy_heavy_has_higher_liquidity(self, state_with_risk):
        tsy_heavy = await self._call(state_with_risk, 10, 10, 80)
        mbs_heavy = await self._call(state_with_risk, 80, 10, 10)
        assert tsy_heavy["projected_liquidity_score"] > mbs_heavy["projected_liquidity_score"]

    async def test_within_bounds_flag_present(self, state_with_risk):
        result = await self._call(state_with_risk, 60, 22, 18)
        assert "within_duration_bounds" in result

    async def test_error_when_weights_dont_sum_to_100(self, state_with_risk):
        args = json.dumps({"mbs_pct": 50, "cmbs_pct": 50, "treasury_pct": 50, "new_volume_mm": 500})
        result = json.loads(
            await estimate_duration_impact.on_invoke_tool(make_ctx(state_with_risk), args)
        )
        assert "error" in result

    async def test_runs_without_risk_constraints(self, state_with_volumes):
        """Should still return a result when risk_constraints is None."""
        result = await self._call(state_with_volumes, 60, 22, 18)
        assert "projected_portfolio_duration" in result


# ---------------------------------------------------------------------------
# get_risk_constraints_summary
# ---------------------------------------------------------------------------

class TestGetRiskConstraintsSummary:
    async def test_returns_json_when_constraints_set(self, state_with_risk):
        result = json.loads(
            await get_risk_constraints_summary.on_invoke_tool(make_ctx(state_with_risk), "{}")
        )
        assert "duration_min" in result
        assert "duration_max" in result

    async def test_returns_error_when_no_constraints(self, bare_state):
        result = json.loads(
            await get_risk_constraints_summary.on_invoke_tool(make_ctx(bare_state), "{}")
        )
        assert "error" in result

    async def test_returns_correct_values(self, state_with_risk):
        result = json.loads(
            await get_risk_constraints_summary.on_invoke_tool(make_ctx(state_with_risk), "{}")
        )
        assert result["duration_min"] == state_with_risk.risk_constraints.duration_min
        assert result["duration_max"] == state_with_risk.risk_constraints.duration_max
