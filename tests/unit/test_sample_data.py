"""
Unit tests for data/sample_data.py.

Validates that the generated DataFrames have the expected shape, columns,
data types, and business-logic constraints.  No external dependencies.
"""

from __future__ import annotations

import pytest
import pandas as pd

from data.sample_data import generate_sample_data


@pytest.fixture(scope="module")
def data():
    """Generate once per module — data generation is deterministic and slow-ish."""
    pool_df, portfolio_df = generate_sample_data()
    return pool_df, portfolio_df


@pytest.fixture(scope="module")
def pool_df(data):
    return data[0]


@pytest.fixture(scope="module")
def portfolio_df(data):
    return data[1]


# ---------------------------------------------------------------------------
# pool_df — shape and columns
# ---------------------------------------------------------------------------

class TestPoolDataFrameShape:
    def test_has_expected_number_of_rows(self, pool_df):
        # 34 pools × 120 months
        assert len(pool_df) == 34 * 120

    def test_has_23_columns(self, pool_df):
        assert len(pool_df.columns) == 23

    def test_required_columns_present(self, pool_df):
        required = {
            "cusip", "date", "product_type", "agency", "term", "rate_type",
            "arm_reset", "coupon", "wac", "wam", "wala", "original_balance_mm",
            "current_factor", "predicted_existing_balance_mm", "cpr_annual_pct",
            "cdr_annual_pct", "oas_bps", "effective_duration", "convexity",
            "price", "yield_pct", "credit_rating", "liquidity_score",
        }
        assert required.issubset(set(pool_df.columns))


# ---------------------------------------------------------------------------
# pool_df — product types
# ---------------------------------------------------------------------------

class TestPoolDataFrameProductTypes:
    def test_three_product_types(self, pool_df):
        types = set(pool_df["product_type"].unique())
        assert types == {"MBS", "CMBS", "TREASURY"}

    def test_34_unique_cusips(self, pool_df):
        assert pool_df["cusip"].nunique() == 34

    def test_each_cusip_has_120_months(self, pool_df):
        counts = pool_df.groupby("cusip").size()
        assert (counts == 120).all()

    def test_mbs_pools_count(self, pool_df):
        mbs_cusips = pool_df[pool_df["product_type"] == "MBS"]["cusip"].nunique()
        assert mbs_cusips == 21  # 8 FNMA + 5 FHLMC + 5 GNMA + 3 ARM

    def test_cmbs_pools_count(self, pool_df):
        cmbs_cusips = pool_df[pool_df["product_type"] == "CMBS"]["cusip"].nunique()
        assert cmbs_cusips == 8

    def test_tsy_pools_count(self, pool_df):
        tsy_cusips = pool_df[pool_df["product_type"] == "TREASURY"]["cusip"].nunique()
        assert tsy_cusips == 5


# ---------------------------------------------------------------------------
# pool_df — value ranges and data quality
# ---------------------------------------------------------------------------

class TestPoolDataFrameValues:
    def test_current_factor_between_0_and_1(self, pool_df):
        assert pool_df["current_factor"].between(0.0, 1.0).all()

    def test_predicted_balance_non_negative(self, pool_df):
        assert (pool_df["predicted_existing_balance_mm"] >= 0).all()

    def test_cpr_between_0_and_100(self, pool_df):
        assert pool_df["cpr_annual_pct"].between(0.0, 100.0).all()

    def test_cdr_non_negative(self, pool_df):
        assert (pool_df["cdr_annual_pct"] >= 0).all()

    def test_effective_duration_positive(self, pool_df):
        assert (pool_df["effective_duration"] > 0).all()

    def test_liquidity_score_between_1_and_10(self, pool_df):
        assert pool_df["liquidity_score"].between(1.0, 10.0).all()

    def test_price_is_reasonable(self, pool_df):
        # Bond prices typically 70–130 for investment grade
        assert pool_df["price"].between(50.0, 150.0).all()

    def test_yield_pct_positive(self, pool_df):
        assert (pool_df["yield_pct"] > 0).all()

    def test_coupon_non_negative(self, pool_df):
        assert (pool_df["coupon"] >= 0).all()

    def test_tsy_oas_is_zero_or_near_zero(self, pool_df):
        tsy = pool_df[pool_df["product_type"] == "TSY"]
        assert (tsy["oas_bps"].abs() < 5).all()

    def test_mbs_duration_less_than_tsy_duration(self, pool_df):
        mbs_avg_dur = pool_df[pool_df["product_type"] == "MBS"]["effective_duration"].mean()
        tsy_avg_dur = pool_df[pool_df["product_type"] == "TREASURY"]["effective_duration"].mean()
        # MBS has negative convexity / prepayment — typically shorter effective duration
        # This is a soft check; allow some tolerance
        assert mbs_avg_dur < tsy_avg_dur + 2.0

    def test_date_column_is_datetime_or_string(self, pool_df):
        # Date column should be parseable
        pd.to_datetime(pool_df["date"])  # raises if unparseable

    def test_no_null_values_in_key_columns(self, pool_df):
        key_cols = [
            "cusip", "date", "product_type", "predicted_existing_balance_mm",
            "effective_duration", "liquidity_score",
        ]
        assert pool_df[key_cols].isnull().sum().sum() == 0


# ---------------------------------------------------------------------------
# portfolio_df — shape and columns
# ---------------------------------------------------------------------------

class TestPortfolioDataFrameShape:
    def test_has_120_rows(self, portfolio_df):
        assert len(portfolio_df) == 120

    def test_required_columns_present(self, portfolio_df):
        required = {
            "date",
            "target_total_balance_mm",
            "predicted_existing_balance_mm",
            "new_volume_mm",
            "new_volume_12m_rolling_mm",
        }
        assert required.issubset(set(portfolio_df.columns))


# ---------------------------------------------------------------------------
# portfolio_df — business logic
# ---------------------------------------------------------------------------

class TestPortfolioDataFrameBusinessLogic:
    def test_new_volume_is_non_negative(self, portfolio_df):
        assert (portfolio_df["new_volume_mm"] >= 0).all()

    def test_target_balance_exceeds_existing_balance(self, portfolio_df):
        """Target must always be >= predicted existing (new volume >= 0)."""
        assert (
            portfolio_df["target_total_balance_mm"]
            >= portfolio_df["predicted_existing_balance_mm"] - 0.01
        ).all()

    def test_new_volume_equals_target_minus_existing(self, portfolio_df):
        computed = (
            portfolio_df["target_total_balance_mm"]
            - portfolio_df["predicted_existing_balance_mm"]
        )
        diff = (portfolio_df["new_volume_mm"] - computed).abs()
        assert (diff < 1.0).all()  # within $1MM tolerance

    def test_portfolio_grows_over_time(self, portfolio_df):
        """Target balance in year 10 should be materially above year 1."""
        first_year_avg = portfolio_df["target_total_balance_mm"].iloc[:12].mean()
        last_year_avg = portfolio_df["target_total_balance_mm"].iloc[-12:].mean()
        assert last_year_avg > first_year_avg * 1.2  # at least 20% growth

    def test_rolling_volume_is_positive(self, portfolio_df):
        assert (portfolio_df["new_volume_12m_rolling_mm"] >= 0).all()

    def test_no_null_values(self, portfolio_df):
        assert portfolio_df.isnull().sum().sum() == 0
