"""
Shared configuration for integration tests.

All integration tests require a live OpenAI API key.  If OPENAI_API_KEY is
not set the entire suite is skipped, so CI can safely run without credentials.

Run integration tests explicitly:
    uv run pytest tests/integration -v
"""

from __future__ import annotations

import os

import pytest

from data.sample_data import generate_sample_data
from models.workflow_state import RiskAppetite, WorkflowState
from persistence.state_manager import StateManager


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require OPENAI_API_KEY)",
    )


def pytest_collection_modifyitems(config, items):
    """Auto-skip all tests in this package if no API key is set."""
    if os.getenv("OPENAI_API_KEY"):
        return
    skip = pytest.mark.skip(reason="OPENAI_API_KEY not set — skipping integration tests")
    for item in items:
        if "integration" in str(item.fspath):
            item.add_marker(skip)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sample_data():
    """Generate sample data once per test session."""
    return generate_sample_data()


@pytest.fixture()
def fresh_state(tmp_path, sample_data) -> WorkflowState:
    """
    A fully populated WorkflowState ready for agent runs.

    monthly_volumes and pool_summary are loaded from synthetic data so agents
    have realistic context without touching any real portfolio system.
    """
    pool_df, portfolio_df = sample_data
    manager = StateManager(state_dir=str(tmp_path))
    state = manager.new_state(trader_name="Integration Tester", risk_appetite=RiskAppetite.MODERATE)

    # Load monthly volumes (same logic as orchestrator._load_data_into_state)
    from models.workflow_state import MonthlyVolume
    vols = []
    for _, row in portfolio_df.iterrows():
        vols.append(MonthlyVolume(
            date=str(row["date"])[:10],
            target_total_balance_mm=float(row["target_total_balance_mm"]),
            predicted_existing_balance_mm=float(row["predicted_existing_balance_mm"]),
            new_volume_mm=float(row["new_volume_mm"]),
        ))
    state.monthly_volumes = vols

    # Build pool summary (same logic as orchestrator._build_pool_summary)
    summary_rows = []
    for pt in pool_df["product_type"].unique():
        sub = pool_df[pool_df["product_type"] == pt]
        summary_rows.append({
            "product_type": pt,
            "avg_duration": float(sub["effective_duration"].mean()),
            "avg_liquidity_score": float(sub["liquidity_score"].mean()),
            "avg_oas_bps": float(sub["oas_bps"].mean()),
            "avg_coupon": float(sub["coupon"].mean()),
            "total_balance_mm": float(sub["predicted_existing_balance_mm"].iloc[-1]),
        })
    state.pool_summary = {
        "by_product_type": {r["product_type"]: r for r in summary_rows},
        "total_pools": int(pool_df["cusip"].nunique()),
        "total_balance_mm": sum(r["total_balance_mm"] for r in summary_rows),
    }

    return state
