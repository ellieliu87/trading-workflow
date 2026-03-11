"""
Unit tests for persistence/state_manager.py.

Uses a temporary directory so no real workflow_states/ files are touched.
"""

from __future__ import annotations

import pytest

from models.workflow_state import (
    ApprovalStatus,
    GateDecision,
    RiskAppetite,
    WorkflowPhase,
    WorkflowState,
)
from persistence.state_manager import StateManager


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

@pytest.fixture()
def manager(tmp_path):
    """StateManager pointed at a temporary directory."""
    return StateManager(state_dir=str(tmp_path))


# ---------------------------------------------------------------------------
# new_state
# ---------------------------------------------------------------------------

class TestNewState:
    def test_returns_workflow_state(self, manager):
        state = manager.new_state()
        assert isinstance(state, WorkflowState)

    def test_session_id_is_non_empty(self, manager):
        state = manager.new_state()
        assert state.session_id != ""

    def test_session_id_format(self, manager):
        state = manager.new_state()
        # Format: YYYYMMdd_HHMMSS_hex6
        parts = state.session_id.split("_")
        assert len(parts) == 3
        assert len(parts[0]) == 8   # date
        assert len(parts[1]) == 6   # time
        assert len(parts[2]) == 6   # hex

    def test_default_risk_appetite(self, manager):
        state = manager.new_state()
        assert state.risk_appetite == RiskAppetite.MODERATE

    def test_custom_risk_appetite(self, manager):
        state = manager.new_state(risk_appetite=RiskAppetite.AGGRESSIVE)
        assert state.risk_appetite == RiskAppetite.AGGRESSIVE

    def test_custom_trader_name(self, manager):
        state = manager.new_state(trader_name="Alice")
        assert state.trader_name == "Alice"

    def test_initial_phase_is_init(self, manager):
        state = manager.new_state()
        assert state.phase == WorkflowPhase.INIT

    def test_two_states_have_different_session_ids(self, manager):
        s1 = manager.new_state()
        s2 = manager.new_state()
        assert s1.session_id != s2.session_id


# ---------------------------------------------------------------------------
# save and load
# ---------------------------------------------------------------------------

class TestSaveAndLoad:
    async def test_save_creates_file(self, manager, tmp_path):
        state = manager.new_state()
        await manager.save(state)
        assert (tmp_path / f"{state.session_id}.json").exists()

    async def test_save_creates_latest_file(self, manager, tmp_path):
        state = manager.new_state()
        await manager.save(state)
        assert (tmp_path / "_latest.json").exists()

    async def test_load_returns_none_for_missing_session(self, manager):
        result = await manager.load("nonexistent_session_id")
        assert result is None

    async def test_load_round_trip(self, manager):
        state = manager.new_state(trader_name="Bob", risk_appetite=RiskAppetite.CONSERVATIVE)
        await manager.save(state)
        loaded = await manager.load(state.session_id)
        assert loaded is not None
        assert loaded.session_id == state.session_id
        assert loaded.trader_name == "Bob"
        assert loaded.risk_appetite == RiskAppetite.CONSERVATIVE

    async def test_load_preserves_phase(self, manager):
        state = manager.new_state()
        state.advance_phase(WorkflowPhase.RISK_ASSESSMENT)
        await manager.save(state)
        loaded = await manager.load(state.session_id)
        assert loaded.phase == WorkflowPhase.RISK_ASSESSMENT

    async def test_load_preserves_gate_decisions(self, manager):
        state = manager.new_state()
        state.add_gate_decision(GateDecision(gate_name="gate_1", status=ApprovalStatus.APPROVED))
        await manager.save(state)
        loaded = await manager.load(state.session_id)
        assert len(loaded.gate_decisions) == 1
        assert loaded.gate_decisions[0].gate_name == "gate_1"

    async def test_save_updates_updated_at(self, manager):
        state = manager.new_state()
        original_updated_at = state.updated_at
        await manager.save(state)
        assert state.updated_at >= original_updated_at


# ---------------------------------------------------------------------------
# load_latest
# ---------------------------------------------------------------------------

class TestLoadLatest:
    async def test_load_latest_returns_none_when_no_sessions(self, manager):
        result = await manager.load_latest()
        assert result is None

    async def test_load_latest_returns_last_saved(self, manager):
        s1 = manager.new_state(trader_name="First")
        await manager.save(s1)
        s2 = manager.new_state(trader_name="Second")
        await manager.save(s2)
        latest = await manager.load_latest()
        assert latest is not None
        assert latest.trader_name == "Second"


# ---------------------------------------------------------------------------
# list_sessions
# ---------------------------------------------------------------------------

class TestListSessions:
    async def test_empty_directory_returns_empty_list(self, manager):
        assert manager.list_sessions() == []

    async def test_saved_sessions_appear_in_list(self, manager):
        state = manager.new_state(trader_name="Charlie")
        await manager.save(state)
        sessions = manager.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == state.session_id

    async def test_list_excludes_latest_file(self, manager):
        state = manager.new_state()
        await manager.save(state)
        sessions = manager.list_sessions()
        # _latest.json should not appear
        for s in sessions:
            assert not s.get("file", "").startswith("_")

    async def test_list_contains_phase_and_trader(self, manager):
        state = manager.new_state(trader_name="Diana")
        await manager.save(state)
        sessions = manager.list_sessions()
        assert sessions[0]["trader_name"] == "Diana"
        assert "phase" in sessions[0]

    async def test_multiple_sessions_all_listed(self, manager):
        for i in range(3):
            state = manager.new_state(trader_name=f"Trader{i}")
            await manager.save(state)
        sessions = manager.list_sessions()
        assert len(sessions) == 3
