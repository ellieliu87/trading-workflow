"""Unit tests for models/workflow_state.py."""

from __future__ import annotations

import json

import pytest

from models.workflow_state import (
    ApprovalStatus,
    GateDecision,
    MBSBreakdown,
    MonthlyVolume,
    RiskAppetite,
    RiskConstraints,
    WorkflowPhase,
    WorkflowState,
)


# ---------------------------------------------------------------------------
# WorkflowState construction
# ---------------------------------------------------------------------------

class TestWorkflowStateDefaults:
    def test_phase_defaults_to_init(self) -> None:
        state = WorkflowState(session_id="s1")
        assert state.phase == WorkflowPhase.INIT

    def test_risk_appetite_defaults_to_moderate(self) -> None:
        state = WorkflowState(session_id="s1")
        assert state.risk_appetite == RiskAppetite.MODERATE

    def test_trader_name_defaults(self) -> None:
        state = WorkflowState(session_id="s1")
        assert state.trader_name == "Trader"

    def test_gate_decisions_empty(self) -> None:
        state = WorkflowState(session_id="s1")
        assert state.gate_decisions == []

    def test_monthly_volumes_empty(self) -> None:
        state = WorkflowState(session_id="s1")
        assert state.monthly_volumes == []

    def test_risk_constraints_none(self) -> None:
        state = WorkflowState(session_id="s1")
        assert state.risk_constraints is None

    def test_selected_scenario_none(self) -> None:
        state = WorkflowState(session_id="s1")
        assert state.selected_scenario is None

    def test_custom_risk_appetite(self) -> None:
        state = WorkflowState(session_id="s1", risk_appetite=RiskAppetite.AGGRESSIVE)
        assert state.risk_appetite == RiskAppetite.AGGRESSIVE


# ---------------------------------------------------------------------------
# advance_phase
# ---------------------------------------------------------------------------

class TestAdvancePhase:
    def test_advance_from_init_to_new_volume(self) -> None:
        state = WorkflowState(session_id="s1")
        state.advance_phase(WorkflowPhase.NEW_VOLUME)
        assert state.phase == WorkflowPhase.NEW_VOLUME

    def test_advance_updates_updated_at(self) -> None:
        state = WorkflowState(session_id="s1")
        before = state.updated_at
        state.advance_phase(WorkflowPhase.RISK_ASSESSMENT)
        # updated_at may be equal (same second) but should not be earlier
        assert state.updated_at >= before

    def test_advance_full_sequence(self) -> None:
        state = WorkflowState(session_id="s1")
        sequence = [
            WorkflowPhase.NEW_VOLUME,
            WorkflowPhase.RISK_ASSESSMENT,
            WorkflowPhase.ALLOCATION,
            WorkflowPhase.MBS_DECOMPOSITION,
            WorkflowPhase.FINAL_APPROVAL,
            WorkflowPhase.COMPLETE,
        ]
        for phase in sequence:
            state.advance_phase(phase)
            assert state.phase == phase


# ---------------------------------------------------------------------------
# Gate decisions
# ---------------------------------------------------------------------------

class TestGateDecisions:
    def test_add_gate_decision_appends(self) -> None:
        state = WorkflowState(session_id="s1")
        d = GateDecision(gate_name="gate_new_volume", status=ApprovalStatus.APPROVED)
        state.add_gate_decision(d)
        assert len(state.gate_decisions) == 1

    def test_add_multiple_decisions(self) -> None:
        state = WorkflowState(session_id="s1")
        for i in range(3):
            state.add_gate_decision(
                GateDecision(gate_name=f"gate_{i}", status=ApprovalStatus.APPROVED)
            )
        assert len(state.gate_decisions) == 3

    def test_last_decision_for_returns_correct(self) -> None:
        state = WorkflowState(session_id="s1")
        state.add_gate_decision(GateDecision(gate_name="gate_new_volume", status=ApprovalStatus.APPROVED))
        state.add_gate_decision(GateDecision(gate_name="gate_risk", status=ApprovalStatus.MODIFIED))
        result = state.last_decision_for("gate_risk")
        assert result is not None
        assert result.status == ApprovalStatus.MODIFIED

    def test_last_decision_returns_most_recent_of_same_gate(self) -> None:
        state = WorkflowState(session_id="s1")
        state.add_gate_decision(GateDecision(gate_name="gate_new_volume", status=ApprovalStatus.MODIFIED))
        state.add_gate_decision(GateDecision(gate_name="gate_new_volume", status=ApprovalStatus.APPROVED))
        result = state.last_decision_for("gate_new_volume")
        assert result.status == ApprovalStatus.APPROVED

    def test_last_decision_for_missing_gate_returns_none(self) -> None:
        state = WorkflowState(session_id="s1")
        assert state.last_decision_for("nonexistent") is None


# ---------------------------------------------------------------------------
# Serialisation round-trip
# ---------------------------------------------------------------------------

class TestSerialisationRoundTrip:
    def test_basic_round_trip(self) -> None:
        state = WorkflowState(session_id="rt_001", trader_name="Jane")
        restored = WorkflowState.model_validate_json(state.model_dump_json())
        assert restored.session_id == "rt_001"
        assert restored.trader_name == "Jane"
        assert restored.phase == WorkflowPhase.INIT

    def test_round_trip_with_gate_decisions(self) -> None:
        state = WorkflowState(session_id="rt_002")
        state.add_gate_decision(GateDecision(gate_name="g1", status=ApprovalStatus.APPROVED))
        restored = WorkflowState.model_validate_json(state.model_dump_json())
        assert len(restored.gate_decisions) == 1
        assert restored.gate_decisions[0].gate_name == "g1"

    def test_round_trip_with_risk_constraints(self) -> None:
        state = WorkflowState(session_id="rt_003")
        state.risk_constraints = RiskConstraints(duration_min=4.0, duration_max=7.0)
        restored = WorkflowState.model_validate_json(state.model_dump_json())
        assert restored.risk_constraints is not None
        assert restored.risk_constraints.duration_min == 4.0

    def test_round_trip_with_monthly_volumes(self) -> None:
        state = WorkflowState(session_id="rt_004")
        state.monthly_volumes = [
            MonthlyVolume(date="2026-01-01", target_total_balance_mm=10_000,
                          predicted_existing_balance_mm=9_700, new_volume_mm=300),
        ]
        restored = WorkflowState.model_validate_json(state.model_dump_json())
        assert len(restored.monthly_volumes) == 1
        assert restored.monthly_volumes[0].new_volume_mm == 300.0

    def test_model_dump_json_is_valid_json(self) -> None:
        state = WorkflowState(session_id="rt_005", risk_appetite=RiskAppetite.CONSERVATIVE)
        raw = state.model_dump_json()
        parsed = json.loads(raw)
        assert parsed["risk_appetite"] == "conservative"


# ---------------------------------------------------------------------------
# RiskConstraints model
# ---------------------------------------------------------------------------

class TestRiskConstraints:
    def test_defaults(self) -> None:
        rc = RiskConstraints()
        assert rc.duration_min == 3.5
        assert rc.duration_max == 6.5
        assert rc.max_cmbs_pct == 30.0

    def test_notes_defaults_empty(self) -> None:
        rc = RiskConstraints()
        assert rc.notes == []

    def test_custom_values(self) -> None:
        rc = RiskConstraints(duration_min=4.0, duration_max=7.5, max_arm_pct=15.0)
        assert rc.duration_min == 4.0
        assert rc.max_arm_pct == 15.0


# ---------------------------------------------------------------------------
# MBSBreakdown model
# ---------------------------------------------------------------------------

class TestMBSBreakdown:
    def test_all_pcts_default_to_zero(self) -> None:
        mb = MBSBreakdown()
        assert mb.fnma_fixed_30yr_pct == 0.0
        assert mb.arm_pct == 0.0

    def test_pct_values_are_stored(self) -> None:
        mb = MBSBreakdown(fnma_fixed_30yr_pct=40.0, arm_pct=5.0)
        assert mb.fnma_fixed_30yr_pct == 40.0
        assert mb.arm_pct == 5.0
