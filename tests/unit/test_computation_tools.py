"""
Unit tests for tools/computation.py.

Tools are invoked via tool.on_invoke_tool(ctx, args_json) which is the same
path the agent runtime uses.  No OpenAI API calls are made.
"""

from __future__ import annotations

import json

import pytest

from tests.conftest import make_ctx
from tools.computation import (
    compute_new_volume_schedule,
    compute_volume_timing_analysis,
    summarise_pool_universe,
)


# ---------------------------------------------------------------------------
# compute_new_volume_schedule
# ---------------------------------------------------------------------------

class TestComputeNewVolumeSchedule:
    async def test_returns_valid_json(self, state_with_volumes):
        result = json.loads(
            await compute_new_volume_schedule.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        assert isinstance(result, dict)

    async def test_contains_required_keys(self, state_with_volumes):
        result = json.loads(
            await compute_new_volume_schedule.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        assert "next_12m_new_volume_mm" in result
        assert "total_10yr_new_volume_mm" in result
        assert "annual_totals_mm" in result
        assert "first_24_months" in result

    async def test_12m_total_is_positive(self, state_with_volumes):
        result = json.loads(
            await compute_new_volume_schedule.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        assert result["next_12m_new_volume_mm"] > 0

    async def test_10yr_total_greater_than_12m(self, state_with_volumes):
        result = json.loads(
            await compute_new_volume_schedule.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        assert result["total_10yr_new_volume_mm"] > result["next_12m_new_volume_mm"]

    async def test_first_24_months_has_24_entries(self, state_with_volumes):
        result = json.loads(
            await compute_new_volume_schedule.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        assert len(result["first_24_months"]) == 24

    async def test_first_24_entries_have_required_fields(self, state_with_volumes):
        result = json.loads(
            await compute_new_volume_schedule.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        for entry in result["first_24_months"]:
            assert "date" in entry
            assert "new_volume_mm" in entry
            assert "target_mm" in entry
            assert "predicted_existing_mm" in entry

    async def test_state_is_updated(self, state_with_volumes):
        await compute_new_volume_schedule.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        assert state_with_volumes.next_12m_new_volume_mm > 0
        assert state_with_volumes.total_10yr_new_volume_mm > 0

    async def test_annual_totals_has_10_years(self, state_with_volumes):
        result = json.loads(
            await compute_new_volume_schedule.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        assert len(result["annual_totals_mm"]) == 10

    async def test_error_when_no_volumes(self, bare_state):
        result = json.loads(
            await compute_new_volume_schedule.on_invoke_tool(make_ctx(bare_state), "{}")
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# summarise_pool_universe
# ---------------------------------------------------------------------------

class TestSummarisePoolUniverse:
    async def test_returns_valid_json(self, state_with_pool_summary):
        result = json.loads(
            await summarise_pool_universe.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        )
        assert isinstance(result, dict)

    async def test_contains_product_types(self, state_with_pool_summary):
        result = json.loads(
            await summarise_pool_universe.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        )
        assert "by_product_type" in result
        types = set(result["by_product_type"].keys())
        assert types == {"MBS", "CMBS", "TREASURY"}

    async def test_total_balance_is_positive(self, state_with_pool_summary):
        result = json.loads(
            await summarise_pool_universe.on_invoke_tool(make_ctx(state_with_pool_summary), "{}")
        )
        assert result["total_balance_mm"] > 0

    async def test_error_when_no_pool_summary(self, bare_state):
        result = json.loads(
            await summarise_pool_universe.on_invoke_tool(make_ctx(bare_state), "{}")
        )
        assert "error" in result


# ---------------------------------------------------------------------------
# compute_volume_timing_analysis
# ---------------------------------------------------------------------------

class TestComputeVolumeTimingAnalysis:
    async def test_returns_valid_json(self, state_with_volumes):
        result = json.loads(
            await compute_volume_timing_analysis.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        assert isinstance(result, dict)

    async def test_contains_buckets(self, state_with_volumes):
        result = json.loads(
            await compute_volume_timing_analysis.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        assert "buckets" in result
        assert len(result["buckets"]) > 0

    async def test_default_horizon_is_36(self, state_with_volumes):
        result = json.loads(
            await compute_volume_timing_analysis.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        assert result["horizon_months"] == 36

    async def test_custom_horizon(self, state_with_volumes):
        args = json.dumps({"horizon_months": 12})
        result = json.loads(
            await compute_volume_timing_analysis.on_invoke_tool(make_ctx(state_with_volumes), args)
        )
        assert result["horizon_months"] == 12

    async def test_horizon_capped_at_volume_length(self, state_with_volumes):
        args = json.dumps({"horizon_months": 9999})
        result = json.loads(
            await compute_volume_timing_analysis.on_invoke_tool(make_ctx(state_with_volumes), args)
        )
        assert result["horizon_months"] <= len(state_with_volumes.monthly_volumes)

    async def test_each_bucket_has_total_and_avg(self, state_with_volumes):
        result = json.loads(
            await compute_volume_timing_analysis.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        for bucket in result["buckets"].values():
            assert "total_mm" in bucket
            assert "avg_monthly_mm" in bucket
            assert "months" in bucket

    async def test_avg_monthly_matches_total(self, state_with_volumes):
        result = json.loads(
            await compute_volume_timing_analysis.on_invoke_tool(make_ctx(state_with_volumes), "{}")
        )
        for bucket in result["buckets"].values():
            n = len(bucket["months"])
            expected_avg = round(bucket["total_mm"] / n, 2) if n else 0.0
            assert abs(bucket["avg_monthly_mm"] - expected_avg) < 0.01

    async def test_error_when_no_volumes(self, bare_state):
        result = json.loads(
            await compute_volume_timing_analysis.on_invoke_tool(make_ctx(bare_state), "{}")
        )
        assert "error" in result
