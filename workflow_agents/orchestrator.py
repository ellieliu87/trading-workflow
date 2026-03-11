"""
Trading Workflow Orchestrator

Manages the full lifecycle:
  Phase 1 → NewVolumeAgent      → Gate 1 (trader confirms purchase schedule)
  Phase 2 → RiskAgent           → Gate 2 (trader confirms risk bounds)
  Phase 3 → AllocationAgent     → Gate 3 (trader selects allocation scenario)
  Phase 4 → MBSDecompositionAgent → Gate 4 (trader approves MBS breakdown)
  Phase 5 → Final               → Gate 5 (trader gives final sign-off)

State is persisted to disk after every gate.
Arize Phoenix traces every agent run.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

import pandas as pd
from agents import Runner
from rich.console import Console
from rich.panel import Panel

from workflow_agents.allocation_agent import build_allocation_agent
from workflow_agents.mbs_decomposition_agent import build_mbs_decomposition_agent
from workflow_agents.new_volume_agent import build_new_volume_agent
from workflow_agents.risk_agent import build_risk_agent
from data.sample_data import generate_sample_data, get_pool_summary
from models.workflow_state import (
    ApprovalStatus,
    RiskAppetite,
    WorkflowPhase,
    WorkflowState,
)
from persistence.state_manager import StateManager
from tools.human_loop import (
    gate_allocation,
    gate_final_approval,
    gate_mbs_decomposition,
    gate_new_volume,
    gate_risk_assessment,
)

logger = logging.getLogger(__name__)
console = Console(legacy_windows=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_pool_summary(pool_df: pd.DataFrame) -> dict:
    """Compress pool universe DataFrame into a JSON-serialisable summary."""
    by_type: dict[str, Any] = {}
    for pt in pool_df["product_type"].unique():
        sub = pool_df[pool_df["product_type"] == pt]
        by_type[pt] = {
            "cusip_count": int(sub["cusip"].nunique()),
            "total_balance_mm": round(
                float(sub.groupby("cusip")["predicted_existing_balance_mm"].first().sum()), 2
            ),
            "avg_duration": round(float(sub["effective_duration"].mean()), 3),
            "avg_oas_bps": round(float(sub["oas_bps"].mean()), 1),
            "avg_liquidity_score": round(float(sub["liquidity_score"].mean()), 2),
            "avg_coupon": round(float(sub["coupon"].mean()), 3),
            "agencies": sorted(sub["agency"].unique().tolist()),
        }

    latest = pool_df[pool_df["date"] == pool_df["date"].min()]
    return {
        "as_of_date": str(pool_df["date"].min().date()),
        "total_cusips": int(pool_df["cusip"].nunique()),
        "total_balance_mm": round(
            float(latest.groupby("cusip")["predicted_existing_balance_mm"].first().sum()), 2
        ),
        "by_product_type": by_type,
    }


def _phase_banner(phase: WorkflowPhase, msg: str) -> None:
    phase_colours = {
        WorkflowPhase.NEW_VOLUME:        "cyan",
        WorkflowPhase.RISK_ASSESSMENT:   "yellow",
        WorkflowPhase.ALLOCATION:        "blue",
        WorkflowPhase.MBS_DECOMPOSITION: "magenta",
        WorkflowPhase.FINAL_APPROVAL:    "green",
        WorkflowPhase.COMPLETE:          "bold green",
    }
    colour = phase_colours.get(phase, "white")
    console.print(Panel(msg, border_style=colour))


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class TradingWorkflowOrchestrator:
    def __init__(self, state_manager: Optional[StateManager] = None):
        self.state_manager = state_manager or StateManager()
        # Build agents once
        self._new_volume_agent      = build_new_volume_agent()
        self._risk_agent            = build_risk_agent()
        self._allocation_agent      = build_allocation_agent()
        self._mbs_decomp_agent      = build_mbs_decomposition_agent()

    # ── Entry point ──────────────────────────────────────────────────────────

    async def run(
        self,
        resume_session_id: Optional[str] = None,
        trader_name: str = "Trader",
        risk_appetite: RiskAppetite = RiskAppetite.MODERATE,
    ) -> WorkflowState:
        """
        Run or resume the workflow.

        Args:
            resume_session_id: If provided, reload and continue an existing session.
            trader_name:       Trader's display name.
            risk_appetite:     Conservative | Moderate | Aggressive.
        """
        # ── Load or create state ─────────────────────────────────────────────
        if resume_session_id:
            state = await self.state_manager.load(resume_session_id)
            if state is None:
                raise ValueError(f"Session '{resume_session_id}' not found.")
            console.print(Panel(
                f"[bold]Resuming session:[/bold] {state.session_id}\n"
                f"[bold]Phase:[/bold] {state.phase.value}\n"
                f"[bold]Trader:[/bold] {state.trader_name}",
                title="Session Resumed", border_style="yellow",
            ))
        else:
            state = self.state_manager.new_state(trader_name, risk_appetite)
            await self._load_data_into_state(state)
            await self.state_manager.save(state)
            console.print(Panel(
                f"[bold]Session:[/bold]  {state.session_id}\n"
                f"[bold]Trader:[/bold]   {state.trader_name}\n"
                f"[bold]Appetite:[/bold] {state.risk_appetite.value.upper()}\n"
                f"[bold]Volume:[/bold]   {len(state.monthly_volumes)} months loaded\n"
                f"[bold]Pools:[/bold]    {state.pool_summary.get('total_cusips', 0)} CUSIPs",
                title="[bold cyan]Trading Workflow Started[/bold cyan]",
                border_style="cyan",
            ))

        # ── Phase dispatcher ─────────────────────────────────────────────────
        while state.phase not in (WorkflowPhase.COMPLETE,):
            try:
                state = await self._dispatch_phase(state)
            except KeyboardInterrupt:
                console.print("\n[yellow]Workflow paused. State saved. Resume with session ID:[/yellow]")
                console.print(f"  [bold]{state.session_id}[/bold]")
                await self.state_manager.save(state)
                break

        if state.phase == WorkflowPhase.COMPLETE:
            _phase_banner(WorkflowPhase.COMPLETE,
                          f"[bold green]✓ Workflow Complete[/bold green]\n"
                          f"Session: {state.session_id}\n"
                          f"Final summary saved.\n\n"
                          + state.final_summary)

        return state

    # ── Phase dispatcher ─────────────────────────────────────────────────────

    async def _dispatch_phase(self, state: WorkflowState) -> WorkflowState:
        phase = state.phase

        if phase == WorkflowPhase.INIT:
            state.advance_phase(WorkflowPhase.NEW_VOLUME)

        elif phase == WorkflowPhase.NEW_VOLUME:
            state = await self._phase_new_volume(state)

        elif phase == WorkflowPhase.RISK_ASSESSMENT:
            state = await self._phase_risk_assessment(state)

        elif phase == WorkflowPhase.ALLOCATION:
            state = await self._phase_allocation(state)

        elif phase == WorkflowPhase.MBS_DECOMPOSITION:
            state = await self._phase_mbs_decomposition(state)

        elif phase == WorkflowPhase.FINAL_APPROVAL:
            state = await self._phase_final_approval(state)

        await self.state_manager.save(state)
        return state

    # ── Phase 1: New Volume ──────────────────────────────────────────────────

    async def _phase_new_volume(self, state: WorkflowState) -> WorkflowState:
        _phase_banner(WorkflowPhase.NEW_VOLUME,
                      "Phase 1 — New Volume Agent: Calculating purchase schedule...")

        result = await Runner.run(
            self._new_volume_agent,
            "Calculate the full new volume schedule and provide a summary.",
            context=state,
        )
        console.print(f"\n[bold cyan]New Volume Agent:[/bold cyan]\n{result.final_output}\n")

        # Gate 1: Trader confirmation
        decision = await gate_new_volume(state)
        state.add_gate_decision(decision)

        if decision.status == ApprovalStatus.REJECTED:
            console.print("[red]Workflow cancelled at Gate 1.[/red]")
            state.advance_phase(WorkflowPhase.COMPLETE)
        else:
            state.advance_phase(WorkflowPhase.RISK_ASSESSMENT)

        return state

    # ── Phase 2: Risk Assessment ─────────────────────────────────────────────

    async def _phase_risk_assessment(self, state: WorkflowState) -> WorkflowState:
        _phase_banner(WorkflowPhase.RISK_ASSESSMENT,
                      "Phase 2 — Risk Agent: Evaluating portfolio risk profile...")

        prompt = (
            f"Evaluate portfolio risk for a {state.risk_appetite.value} risk appetite. "
            f"New 12-month volume is ${state.next_12m_new_volume_mm:,.1f}MM. "
            "Generate risk constraints and flag any issues."
        )
        result = await Runner.run(
            self._risk_agent,
            prompt,
            context=state,
        )
        console.print(f"\n[bold yellow]Risk Agent:[/bold yellow]\n{result.final_output}\n")

        # Gate 2: Risk confirmation
        decision = await gate_risk_assessment(state)
        state.add_gate_decision(decision)

        if decision.status == ApprovalStatus.REJECTED:
            console.print("[red]Workflow cancelled at Gate 2.[/red]")
            state.advance_phase(WorkflowPhase.COMPLETE)
        else:
            state.advance_phase(WorkflowPhase.ALLOCATION)

        return state

    # ── Phase 3: Allocation ──────────────────────────────────────────────────

    async def _phase_allocation(self, state: WorkflowState) -> WorkflowState:
        _phase_banner(WorkflowPhase.ALLOCATION,
                      "Phase 3 — Allocation Agent: Generating product mix scenarios...")

        prompt = (
            f"Generate allocation scenarios for ${state.next_12m_new_volume_mm:,.1f}MM "
            f"new volume. Risk appetite: {state.risk_appetite.value}. "
            "Present all three scenarios with trade-off analysis."
        )
        result = await Runner.run(
            self._allocation_agent,
            prompt,
            context=state,
        )
        console.print(f"\n[bold blue]Allocation Agent:[/bold blue]\n{result.final_output}\n")

        # Gate 3: Allocation selection
        decision = await gate_allocation(state)
        state.add_gate_decision(decision)

        if decision.status == ApprovalStatus.REJECTED:
            console.print("[red]Workflow cancelled at Gate 3.[/red]")
            state.advance_phase(WorkflowPhase.COMPLETE)
        else:
            state.advance_phase(WorkflowPhase.MBS_DECOMPOSITION)

        return state

    # ── Phase 4: MBS Decomposition ───────────────────────────────────────────

    async def _phase_mbs_decomposition(self, state: WorkflowState) -> WorkflowState:
        _phase_banner(WorkflowPhase.MBS_DECOMPOSITION,
                      "Phase 4 — MBS Decomposition Agent: Breaking down MBS allocation...")

        sc = state.selected_scenario
        prompt = (
            f"Decompose the MBS allocation of ${sc.mbs_mm:,.1f}MM "
            f"(from the {sc.label} scenario). "
            f"Risk appetite: {state.risk_appetite.value}. "
            "Break into Fixed/ARM, FNMA/FHLMC/GNMA, 30YR/15YR. "
            "Then build the full purchase schedule."
        )
        result = await Runner.run(
            self._mbs_decomp_agent,
            prompt,
            context=state,
        )
        console.print(
            f"\n[bold magenta]MBS Decomposition Agent:[/bold magenta]\n{result.final_output}\n"
        )

        # Gate 4: MBS breakdown approval
        decision = await gate_mbs_decomposition(state)
        state.add_gate_decision(decision)

        if decision.status == ApprovalStatus.REJECTED:
            console.print("[red]Workflow cancelled at Gate 4.[/red]")
            state.advance_phase(WorkflowPhase.COMPLETE)
        else:
            state.advance_phase(WorkflowPhase.FINAL_APPROVAL)

        return state

    # ── Phase 5: Final Approval ──────────────────────────────────────────────

    async def _phase_final_approval(self, state: WorkflowState) -> WorkflowState:
        _phase_banner(WorkflowPhase.FINAL_APPROVAL,
                      "Phase 5 — Final Approval: Review and sign off...")

        decision = await gate_final_approval(state)
        state.add_gate_decision(decision)

        if decision.status == ApprovalStatus.REJECTED:
            console.print("[red]Workflow aborted at final approval.[/red]")
            state.advance_phase(WorkflowPhase.COMPLETE)
            state.final_summary = "ABORTED: Trader cancelled at final approval gate."

        elif decision.status == ApprovalStatus.MODIFIED:
            # Trader wants to revise – go back to allocation
            console.print("[yellow]Returning to allocation phase for revision...[/yellow]")
            state.selected_scenario = None
            state.mbs_breakdown = None
            state.purchase_schedule = []
            state.advance_phase(WorkflowPhase.ALLOCATION)

        else:
            # Approved
            state.final_summary = self._build_final_summary(state)
            state.advance_phase(WorkflowPhase.COMPLETE)

        return state

    # ── Helpers ──────────────────────────────────────────────────────────────

    async def _load_data_into_state(self, state: WorkflowState) -> None:
        """Generate sample data and load into workflow state."""
        console.print("[dim]Generating sample portfolio data...[/dim]")
        pool_df, portfolio_df = generate_sample_data(n_months=120)

        # Portfolio projections → monthly_volumes
        from models.workflow_state import MonthlyVolume
        vols = []
        for _, row in portfolio_df.iterrows():
            vols.append(MonthlyVolume(
                date=str(row["date"].date()),
                target_total_balance_mm=float(row["target_total_balance_mm"]),
                predicted_existing_balance_mm=float(row["predicted_existing_balance_mm"]),
                new_volume_mm=float(row["new_volume_mm"]),
            ))
        state.monthly_volumes = vols

        # Pool universe summary
        state.pool_summary = _build_pool_summary(pool_df)
        console.print(
            f"[dim]Loaded {len(vols)} months × "
            f"{state.pool_summary['total_cusips']} CUSIPs[/dim]"
        )

    def _build_final_summary(self, state: WorkflowState) -> str:
        sc  = state.selected_scenario
        mb  = state.mbs_breakdown
        total = sum(i.amount_mm for i in state.purchase_schedule)

        lines = [
            f"TRADING DECISION SUMMARY — {state.session_id}",
            f"Trader: {state.trader_name}  |  Risk Appetite: {state.risk_appetite.value.upper()}",
            f"",
            f"NEW VOLUME (12-Month):  ${state.next_12m_new_volume_mm:,.1f}MM",
            f"TOTAL PURCHASE AMOUNT: ${total:,.1f}MM",
            f"",
            f"ALLOCATION:",
        ]
        if sc:
            lines += [
                f"  MBS:        {sc.mbs_pct:.0f}%  (${sc.mbs_mm:,.1f}MM)",
                f"  CMBS:       {sc.cmbs_pct:.0f}%  (${sc.cmbs_mm:,.1f}MM)",
                f"  Treasuries: {sc.treasury_pct:.0f}%  (${sc.treasury_mm:,.1f}MM)",
                f"  Proj. Duration: {sc.projected_duration:.2f}yr",
                f"  Proj. Yield:    {sc.projected_yield_pct:.2f}%",
            ]
        if mb:
            lines += [
                f"",
                f"MBS BREAKDOWN:",
                f"  FNMA Fixed 30YR:  {mb.fnma_fixed_30yr_pct:.0f}%  (${mb.fnma_fixed_30yr_mm:,.1f}MM)",
                f"  FHLMC Fixed 30YR: {mb.fhlmc_fixed_30yr_pct:.0f}%  (${mb.fhlmc_fixed_30yr_mm:,.1f}MM)",
                f"  GNMA Fixed 30YR:  {mb.gnma_fixed_30yr_pct:.0f}%  (${mb.gnma_fixed_30yr_mm:,.1f}MM)",
                f"  FNMA Fixed 15YR:  {mb.fnma_fixed_15yr_pct:.0f}%  (${mb.fnma_fixed_15yr_mm:,.1f}MM)",
                f"  FHLMC Fixed 15YR: {mb.fhlmc_fixed_15yr_pct:.0f}%  (${mb.fhlmc_fixed_15yr_mm:,.1f}MM)",
                f"  ARM:              {mb.arm_pct:.0f}%  (${mb.arm_mm:,.1f}MM)",
            ]

        # Gate decisions audit trail
        lines += ["", "GATE AUDIT TRAIL:"]
        for gd in state.gate_decisions:
            lines.append(
                f"  [{gd.gate_name:20s}] {gd.status.value:10s} | {gd.timestamp[:19]}"
                + (f" | {gd.notes}" if gd.notes else "")
            )

        return "\n".join(lines)
