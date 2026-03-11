"""
Shared pytest fixtures for the trading workflow test suite.

All tools in this codebase take RunContextWrapper[WorkflowState] as their
first argument and access state via wrapper.context.  The make_ctx() helper
creates a lightweight stand-in accepted by tool.on_invoke_tool().
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from agents.tool_context import ToolContext
from models.workflow_state import (
    AllocationScenario,
    MBSBreakdown,
    MonthlyVolume,
    RiskAppetite,
    RiskConstraints,
    WorkflowPhase,
    WorkflowState,
)


# ---------------------------------------------------------------------------
# Context wrapper mock
# ---------------------------------------------------------------------------

def make_ctx(state: WorkflowState, tool_name: str = "test_tool") -> ToolContext:
    """
    Create a ToolContext suitable for calling tool.on_invoke_tool() in tests.
    ToolContext is a subclass of RunContextWrapper and carries the tool_name,
    tool_call_id, and tool_arguments fields that the SDK requires internally.
    """
    return ToolContext(
        context=state,
        tool_name=tool_name,
        tool_call_id="test_call_id_001",
        tool_arguments="{}",
    )


# ---------------------------------------------------------------------------
# Base state factory
# ---------------------------------------------------------------------------

def _base_state(**kwargs: Any) -> WorkflowState:
    return WorkflowState(session_id="test_session_001", **kwargs)


# ---------------------------------------------------------------------------
# Monthly volume data
# ---------------------------------------------------------------------------

def _make_monthly_volumes(n: int = 120) -> list[MonthlyVolume]:
    """Generate n months of synthetic monthly volume data."""
    volumes = []
    for i in range(n):
        year = 2026 + i // 12
        month = (i % 12) + 1
        volumes.append(MonthlyVolume(
            date=f"{year}-{month:02d}-01",
            target_total_balance_mm=10_000.0 + i * 44.0,
            predicted_existing_balance_mm=9_800.0 - i * 25.0,
            new_volume_mm=max(50.0, 200.0 + i * 69.0),
        ))
    return volumes


# ---------------------------------------------------------------------------
# Pool summary dict
# ---------------------------------------------------------------------------

def _make_pool_summary() -> dict[str, Any]:
    return {
        "by_product_type": {
            "MBS": {
                "avg_duration": 5.2,
                "avg_liquidity_score": 8.8,
                "avg_oas_bps": 45.0,
                "avg_coupon": 4.5,
                "total_balance_mm": 6_370.0,
            },
            "CMBS": {
                "avg_duration": 5.8,
                "avg_liquidity_score": 6.0,
                "avg_oas_bps": 110.0,
                "avg_coupon": 5.1,
                "total_balance_mm": 1_960.0,
            },
            "TREASURY": {
                "avg_duration": 6.0,
                "avg_liquidity_score": 10.0,
                "avg_oas_bps": 0.0,
                "avg_coupon": 3.8,
                "total_balance_mm": 1_470.0,
            },
        },
        "total_pools": 34,
        "total_balance_mm": 9_800.0,
    }


# ---------------------------------------------------------------------------
# Fixtures — progressive state setup
# ---------------------------------------------------------------------------

@pytest.fixture()
def bare_state() -> WorkflowState:
    """Freshly created WorkflowState with no data loaded."""
    return _base_state()


@pytest.fixture()
def state_with_volumes() -> WorkflowState:
    """State with monthly_volumes populated (ready for NewVolumeAgent tools)."""
    state = _base_state()
    state.monthly_volumes = _make_monthly_volumes()
    return state


@pytest.fixture()
def state_with_pool_summary() -> WorkflowState:
    """State with pool_summary populated (ready for RiskAgent tools)."""
    state = _base_state()
    state.monthly_volumes = _make_monthly_volumes()
    state.pool_summary = _make_pool_summary()
    return state


@pytest.fixture()
def state_with_risk(state_with_pool_summary: WorkflowState) -> WorkflowState:
    """State with risk_constraints populated (ready for AllocationAgent tools)."""
    state = state_with_pool_summary
    state.next_12m_new_volume_mm = 5_400.0
    state.total_10yr_new_volume_mm = 54_000.0
    state.risk_constraints = RiskConstraints(
        duration_min=3.8,
        duration_max=6.8,
        current_portfolio_duration=5.35,
        projected_duration_after_purchase=5.35,
        liquidity_score_min=6.0,
        projected_liquidity_score=8.42,
        max_cmbs_pct=30.0,
        max_arm_pct=20.0,
    )
    return state


@pytest.fixture()
def state_with_allocation(state_with_risk: WorkflowState) -> WorkflowState:
    """State with a selected allocation scenario (ready for MBSDecomposition tools)."""
    state = state_with_risk
    scenario = AllocationScenario(
        scenario_id="moderate",
        label="Moderate",
        mbs_pct=60.0,
        cmbs_pct=22.0,
        treasury_pct=18.0,
        mbs_mm=3_240.0,
        cmbs_mm=1_188.0,
        treasury_mm=972.0,
        total_new_volume_mm=5_400.0,
        projected_duration=5.3,
        projected_liquidity_score=8.2,
        projected_yield_pct=5.15,
        rationale="Balanced allocation.",
    )
    state.allocation_scenarios = [scenario]
    state.selected_scenario = scenario
    return state


@pytest.fixture()
def state_with_mbs_breakdown(state_with_allocation: WorkflowState) -> WorkflowState:
    """State with MBSBreakdown populated (ready for build_purchase_schedule)."""
    state = state_with_allocation
    mbs_mm = state.selected_scenario.mbs_mm  # 3240.0
    state.mbs_breakdown = MBSBreakdown(
        fnma_fixed_30yr_pct=40.0,  fnma_fixed_30yr_mm=round(mbs_mm * 0.40, 1),
        fhlmc_fixed_30yr_pct=20.0, fhlmc_fixed_30yr_mm=round(mbs_mm * 0.20, 1),
        gnma_fixed_30yr_pct=15.0,  gnma_fixed_30yr_mm=round(mbs_mm * 0.15, 1),
        fnma_fixed_15yr_pct=15.0,  fnma_fixed_15yr_mm=round(mbs_mm * 0.15, 1),
        fhlmc_fixed_15yr_pct=5.0,  fhlmc_fixed_15yr_mm=round(mbs_mm * 0.05, 1),
        arm_pct=5.0,               arm_mm=round(mbs_mm * 0.05, 1),
        rationale="Balanced MBS sub-bucket breakdown.",
    )
    return state
