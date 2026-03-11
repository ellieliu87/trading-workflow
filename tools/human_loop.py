"""
Human-in-the-loop approval gate mechanics.

Each gate:
  1. Renders a rich CLI panel with the relevant summary.
  2. Prompts the trader for a structured decision.
  3. Validates input and returns a GateDecision.
  4. Supports: APPROVE | MODIFY | REJECT | ALTERNATIVES

Async-safe: uses asyncio.get_event_loop().run_in_executor for blocking input().
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Dict, List, Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from models.workflow_state import (
    AllocationScenario,
    ApprovalStatus,
    GateDecision,
    MBSBreakdown,
    MonthlyVolume,
    PurchaseScheduleItem,
    WorkflowState,
)

console = Console(legacy_windows=False)


# ---------------------------------------------------------------------------
# Low-level async input
# ---------------------------------------------------------------------------

async def _ainput(prompt: str = "") -> str:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, lambda: input(prompt))


async def _prompt_choice(prompt: str, valid: List[str]) -> str:
    while True:
        raw = (await _ainput(prompt)).strip().lower()
        if raw in [v.lower() for v in valid]:
            return raw
        console.print(f"[red]Invalid choice. Options: {', '.join(valid)}[/red]")


# ---------------------------------------------------------------------------
# Gate 1 – New Volume Confirmation
# ---------------------------------------------------------------------------

async def gate_new_volume(state: WorkflowState) -> GateDecision:
    """Display purchase schedule and ask trader to confirm / adjust."""

    console.rule("[bold cyan]GATE 1 — New Volume Confirmation[/bold cyan]")

    # ── Summary table (next 12 months) ───────────────────────────────────────
    t = Table(title="Monthly Purchase Schedule – Next 12 Months", show_lines=True)
    t.add_column("Month",     style="cyan", width=12)
    t.add_column("Target ($MM)",    justify="right", width=14)
    t.add_column("Predicted Existing ($MM)", justify="right", width=22)
    t.add_column("New Volume ($MM)", justify="right", style="green", width=16)

    vols: List[MonthlyVolume] = state.monthly_volumes[:12]
    for v in vols:
        t.add_row(
            v.date[:7],
            f"{v.target_total_balance_mm:,.1f}",
            f"{v.predicted_existing_balance_mm:,.1f}",
            f"[bold]{v.new_volume_mm:,.1f}[/bold]",
        )
    console.print(t)

    # Annual summary
    ann_table = Table(title="Annual New Volume Summary (10-Year)", show_lines=True)
    ann_table.add_column("Year",  style="cyan")
    ann_table.add_column("New Volume ($MM)", justify="right", style="green")
    for i in range(0, min(120, len(state.monthly_volumes)), 12):
        year_vols = state.monthly_volumes[i: i + 12]
        yr_total  = sum(v.new_volume_mm for v in year_vols)
        ann_table.add_row(f"Year {i // 12 + 1}", f"{yr_total:,.1f}")
    console.print(ann_table)

    console.print(Panel(
        f"[bold]Next 12-Month New Volume:[/bold] [green]${state.next_12m_new_volume_mm:,.1f}MM[/green]\n"
        f"[bold]Total 10-Year New Volume:[/bold] [green]${state.total_10yr_new_volume_mm:,.1f}MM[/green]",
        title="Portfolio Summary",
        border_style="green",
    ))

    console.print("\n[bold]Options:[/bold]")
    console.print("  [cyan]A[/cyan]pprove  — proceed with this schedule")
    console.print("  [yellow]M[/yellow]odify   — override total 12M volume (enter custom $MM)")
    console.print("  [red]R[/red]eject   — cancel workflow\n")

    choice = await _prompt_choice("Your choice [A/M/R]: ", ["a", "m", "r"])

    if choice == "r":
        return GateDecision(gate_name="new_volume", status=ApprovalStatus.REJECTED,
                            trader_choice="reject")

    if choice == "a":
        return GateDecision(gate_name="new_volume", status=ApprovalStatus.APPROVED,
                            trader_choice="approve")

    # Modify
    raw_vol = (await _ainput("  Enter custom 12-month new volume ($MM): ")).strip()
    try:
        custom_vol = float(raw_vol)
        state.next_12m_new_volume_mm = custom_vol
        notes_raw = (await _ainput("  Reason for override (press Enter to skip): ")).strip()
        return GateDecision(
            gate_name="new_volume",
            status=ApprovalStatus.MODIFIED,
            trader_choice="modify",
            trader_overrides={"next_12m_new_volume_mm": custom_vol},
            notes=notes_raw,
        )
    except ValueError:
        console.print("[red]Invalid number – approving original schedule.[/red]")
        return GateDecision(gate_name="new_volume", status=ApprovalStatus.APPROVED,
                            trader_choice="approve_fallback")


# ---------------------------------------------------------------------------
# Gate 2 – Risk Assessment Confirmation
# ---------------------------------------------------------------------------

async def gate_risk_assessment(state: WorkflowState) -> GateDecision:
    """Show risk profile and constraints; ask trader to confirm or set custom bounds."""

    console.rule("[bold yellow]GATE 2 — Risk Assessment Review[/bold yellow]")

    rc = state.risk_constraints
    if rc is None:
        console.print("[red]Risk constraints not available.[/red]")
        return GateDecision(gate_name="risk_assessment", status=ApprovalStatus.REJECTED)

    risk_table = Table(title="Portfolio Risk Profile", show_lines=True)
    risk_table.add_column("Metric", style="cyan")
    risk_table.add_column("Current", justify="right")
    risk_table.add_column("Proposed Bounds", justify="right")

    risk_table.add_row(
        "Portfolio Duration (yrs)",
        f"{rc.current_portfolio_duration:.2f}",
        f"{rc.duration_min:.1f} – {rc.duration_max:.1f}",
    )
    risk_table.add_row(
        "Liquidity Score",
        f"{rc.projected_liquidity_score:.1f} / 10",
        f"≥ {rc.liquidity_score_min:.1f}",
    )
    risk_table.add_row(
        "Max CMBS Allocation",
        "—",
        f"≤ {rc.max_cmbs_pct:.0f}%",
    )
    risk_table.add_row(
        "Max ARM Allocation",
        "—",
        f"≤ {rc.max_arm_pct:.0f}%",
    )
    console.print(risk_table)

    if rc.notes:
        console.print("\n[bold yellow]Risk Flags:[/bold yellow]")
        for flag in rc.notes:
            console.print(f"  {flag}")

    console.print(f"\n[bold]Risk Appetite:[/bold] [cyan]{state.risk_appetite.value.upper()}[/cyan]")

    console.print("\n[bold]Options:[/bold]")
    console.print("  [cyan]A[/cyan]ccept  — proceed with current risk bounds")
    console.print("  [yellow]C[/yellow]hange  — override duration bounds or risk appetite")
    console.print("  [red]R[/red]eject  — cancel workflow\n")

    choice = await _prompt_choice("Your choice [A/C/R]: ", ["a", "c", "r"])

    if choice == "r":
        return GateDecision(gate_name="risk_assessment", status=ApprovalStatus.REJECTED)

    if choice == "a":
        return GateDecision(gate_name="risk_assessment", status=ApprovalStatus.APPROVED)

    # Change
    overrides: Dict[str, Any] = {}
    dur_min_raw = (await _ainput(f"  Duration min ({rc.duration_min:.1f}): ")).strip()
    dur_max_raw = (await _ainput(f"  Duration max ({rc.duration_max:.1f}): ")).strip()
    appetite_raw = (await _ainput("  Risk appetite [conservative/moderate/aggressive]: ")).strip().lower()

    if dur_min_raw:
        try:
            rc.duration_min = float(dur_min_raw)
            overrides["duration_min"] = rc.duration_min
        except ValueError:
            pass
    if dur_max_raw:
        try:
            rc.duration_max = float(dur_max_raw)
            overrides["duration_max"] = rc.duration_max
        except ValueError:
            pass
    if appetite_raw in ("conservative", "moderate", "aggressive"):
        from models.workflow_state import RiskAppetite
        state.risk_appetite = RiskAppetite(appetite_raw)
        overrides["risk_appetite"] = appetite_raw

    return GateDecision(
        gate_name="risk_assessment",
        status=ApprovalStatus.MODIFIED,
        trader_choice="change",
        trader_overrides=overrides,
    )


# ---------------------------------------------------------------------------
# Gate 3 – Allocation Approval
# ---------------------------------------------------------------------------

async def gate_allocation(state: WorkflowState) -> GateDecision:
    """Display allocation scenarios; trader selects one or enters custom split."""

    console.rule("[bold blue]GATE 3 — Allocation Approval[/bold blue]")

    if not state.allocation_scenarios:
        console.print("[red]No allocation scenarios generated.[/red]")
        return GateDecision(gate_name="allocation", status=ApprovalStatus.REJECTED)

    # Display each scenario
    for s in state.allocation_scenarios:
        style = "green" if s.scenario_id == state.risk_appetite.value else "white"
        panel_body = (
            f"[bold]MBS:[/bold]       {s.mbs_pct:.0f}%  (${s.mbs_mm:,.1f}MM)\n"
            f"[bold]CMBS:[/bold]      {s.cmbs_pct:.0f}%  (${s.cmbs_mm:,.1f}MM)\n"
            f"[bold]Treasuries:[/bold]{s.treasury_pct:.0f}%  (${s.treasury_mm:,.1f}MM)\n"
            f"─────────────────────────────────\n"
            f"[bold]Proj. Duration:[/bold]       {s.projected_duration:.2f} yrs\n"
            f"[bold]Proj. Liquidity:[/bold]      {s.projected_liquidity_score:.1f} / 10\n"
            f"[bold]Proj. Yield:[/bold]          {s.projected_yield_pct:.2f}%\n"
            f"\n[italic]{s.rationale}[/italic]"
        )
        console.print(Panel(panel_body, title=f"[bold {style}]{s.label}[/bold {style}]",
                            border_style=style))

    console.print("\n[bold]Options:[/bold]")
    console.print("  [cyan]1[/cyan] Conservative")
    console.print("  [cyan]2[/cyan] Moderate")
    console.print("  [cyan]3[/cyan] Aggressive")
    console.print("  [yellow]4[/yellow] Custom split (enter your own percentages)")
    console.print("  [red]5[/red] Reject / cancel\n")

    choice = await _prompt_choice("Select scenario [1/2/3/4/5]: ",
                                  ["1", "2", "3", "4", "5"])

    if choice == "5":
        return GateDecision(gate_name="allocation", status=ApprovalStatus.REJECTED)

    id_map = {"1": "conservative", "2": "moderate", "3": "aggressive"}

    if choice in id_map:
        scenario_id = id_map[choice]
        selected = next(s for s in state.allocation_scenarios if s.scenario_id == scenario_id)
        state.selected_scenario = selected
        return GateDecision(
            gate_name="allocation",
            status=ApprovalStatus.APPROVED,
            trader_choice=scenario_id,
            trader_overrides={"selected_scenario_id": scenario_id},
        )

    # Custom
    console.print("\n  Enter custom allocation (must sum to 100%):")
    mbs_raw  = (await _ainput("  MBS %:        ")).strip()
    cmbs_raw = (await _ainput("  CMBS %:       ")).strip()
    tsy_raw  = (await _ainput("  Treasuries %: ")).strip()
    try:
        mbs_pct = float(mbs_raw)
        cmbs_pct = float(cmbs_raw)
        tsy_pct = float(tsy_raw)
        if abs(mbs_pct + cmbs_pct + tsy_pct - 100) > 1:
            console.print("[red]Does not sum to 100 – defaulting to Moderate.[/red]")
            state.selected_scenario = next(
                s for s in state.allocation_scenarios if s.scenario_id == "moderate"
            )
            return GateDecision(gate_name="allocation", status=ApprovalStatus.APPROVED,
                                trader_choice="moderate_fallback")

        vol = state.next_12m_new_volume_mm
        custom_s = AllocationScenario(
            scenario_id="custom",
            label="Custom",
            mbs_pct=mbs_pct, cmbs_pct=cmbs_pct, treasury_pct=tsy_pct,
            mbs_mm=round(vol * mbs_pct / 100, 1),
            cmbs_mm=round(vol * cmbs_pct / 100, 1),
            treasury_mm=round(vol * tsy_pct / 100, 1),
            total_new_volume_mm=vol,
            projected_duration=5.2,
            projected_liquidity_score=8.0,
            projected_yield_pct=5.1,
            rationale="Trader-defined custom allocation.",
        )
        state.allocation_scenarios.append(custom_s)
        state.selected_scenario = custom_s
        return GateDecision(
            gate_name="allocation",
            status=ApprovalStatus.MODIFIED,
            trader_choice="custom",
            trader_overrides={"mbs_pct": mbs_pct, "cmbs_pct": cmbs_pct, "treasury_pct": tsy_pct},
        )
    except ValueError:
        console.print("[red]Invalid input – defaulting to Moderate.[/red]")
        state.selected_scenario = next(
            s for s in state.allocation_scenarios if s.scenario_id == "moderate"
        )
        return GateDecision(gate_name="allocation", status=ApprovalStatus.APPROVED,
                            trader_choice="moderate_fallback")


# ---------------------------------------------------------------------------
# Gate 4 – MBS Decomposition Approval
# ---------------------------------------------------------------------------

async def gate_mbs_decomposition(state: WorkflowState) -> GateDecision:
    """Display MBS sub-product breakdown and allow trader to adjust weights."""

    console.rule("[bold magenta]GATE 4 — MBS Decomposition Review[/bold magenta]")

    mb = state.mbs_breakdown
    if mb is None:
        console.print("[red]MBS breakdown not available.[/red]")
        return GateDecision(gate_name="mbs_decomposition", status=ApprovalStatus.REJECTED)

    mbs_mm = state.selected_scenario.mbs_mm if state.selected_scenario else 0.0

    t = Table(title=f"MBS Breakdown  (Total: ${mbs_mm:,.1f}MM)", show_lines=True)
    t.add_column("Product",     style="cyan", width=24)
    t.add_column("Agency",      width=8)
    t.add_column("Type",        width=10)
    t.add_column("Pct",         justify="right", width=8)
    t.add_column("Amount ($MM)", justify="right", style="green", width=14)

    rows = [
        ("FNMA Fixed 30YR", "FNMA", "Fixed/30YR", mb.fnma_fixed_30yr_pct,  mb.fnma_fixed_30yr_mm),
        ("FHLMC Fixed 30YR","FHLMC","Fixed/30YR", mb.fhlmc_fixed_30yr_pct, mb.fhlmc_fixed_30yr_mm),
        ("GNMA Fixed 30YR", "GNMA", "Fixed/30YR", mb.gnma_fixed_30yr_pct,  mb.gnma_fixed_30yr_mm),
        ("FNMA Fixed 15YR", "FNMA", "Fixed/15YR", mb.fnma_fixed_15yr_pct,  mb.fnma_fixed_15yr_mm),
        ("FHLMC Fixed 15YR","FHLMC","Fixed/15YR", mb.fhlmc_fixed_15yr_pct, mb.fhlmc_fixed_15yr_mm),
        ("ARM (FNMA 5/1)",  "FNMA", "ARM",        mb.arm_pct,              mb.arm_mm),
    ]
    for name, agency, ptype, pct, amt in rows:
        if pct > 0:
            t.add_row(name, agency, ptype, f"{pct:.0f}%", f"${amt:,.1f}MM")
    console.print(t)

    console.print(Panel(
        f"[italic]{mb.rationale}[/italic]",
        title="Rationale", border_style="magenta",
    ))

    console.print("\n[bold]Options:[/bold]")
    console.print("  [cyan]A[/cyan]pprove  — accept this MBS decomposition")
    console.print("  [yellow]M[/yellow]odify   — enter custom percentages")
    console.print("  [red]R[/red]eject   — cancel\n")

    choice = await _prompt_choice("Your choice [A/M/R]: ", ["a", "m", "r"])

    if choice == "r":
        return GateDecision(gate_name="mbs_decomposition", status=ApprovalStatus.REJECTED)

    if choice == "a":
        return GateDecision(gate_name="mbs_decomposition", status=ApprovalStatus.APPROVED)

    # Modify
    console.print("\n  Re-enter percentages for each sub-product (press Enter to keep current):")

    fields = [
        ("FNMA Fixed 30YR", "fnma_fixed_30yr_pct", mb.fnma_fixed_30yr_pct),
        ("FHLMC Fixed 30YR", "fhlmc_fixed_30yr_pct", mb.fhlmc_fixed_30yr_pct),
        ("GNMA Fixed 30YR", "gnma_fixed_30yr_pct", mb.gnma_fixed_30yr_pct),
        ("FNMA Fixed 15YR", "fnma_fixed_15yr_pct", mb.fnma_fixed_15yr_pct),
        ("FHLMC Fixed 15YR", "fhlmc_fixed_15yr_pct", mb.fhlmc_fixed_15yr_pct),
        ("ARM", "arm_pct", mb.arm_pct),
    ]
    overrides: Dict[str, Any] = {}
    new_pcts: Dict[str, float] = {}

    for label, attr, current in fields:
        raw = (await _ainput(f"  {label} ({current:.0f}%): ")).strip()
        if raw:
            try:
                new_pcts[attr] = float(raw)
                overrides[attr] = float(raw)
            except ValueError:
                new_pcts[attr] = current
        else:
            new_pcts[attr] = current

    total_pct = sum(new_pcts.values())
    if abs(total_pct - 100) > 1:
        console.print(f"[red]Percentages sum to {total_pct:.1f}% – normalising to 100%.[/red]")
        for k in new_pcts:
            new_pcts[k] = new_pcts[k] / total_pct * 100

    # Update state
    for attr, val in new_pcts.items():
        setattr(mb, attr, round(val, 1))
        # Recompute $MM amounts
        amount_attr = attr.replace("_pct", "_mm")
        setattr(mb, amount_attr, round(mbs_mm * val / 100, 1))
    mb.rationale = "Trader-adjusted MBS decomposition."

    return GateDecision(
        gate_name="mbs_decomposition",
        status=ApprovalStatus.MODIFIED,
        trader_choice="modify",
        trader_overrides=overrides,
    )


# ---------------------------------------------------------------------------
# Gate 5 – Final Approval
# ---------------------------------------------------------------------------

async def gate_final_approval(state: WorkflowState) -> GateDecision:
    """Show the complete purchase schedule and get final sign-off."""

    console.rule("[bold green]GATE 5 — Final Purchase Schedule Approval[/bold green]")

    t = Table(title="Final Purchase Schedule", show_lines=True)
    t.add_column("#", width=4)
    t.add_column("Product", style="cyan", width=22)
    t.add_column("Sub-Type", width=18)
    t.add_column("Amount ($MM)", justify="right", style="green", width=14)
    t.add_column("Coupon Range", width=14)
    t.add_column("Target Dur", justify="right", width=10)
    t.add_column("Target OAS", justify="right", width=10)

    total = 0.0
    for item in state.purchase_schedule:
        t.add_row(
            str(item.priority),
            item.product_type,
            item.sub_type,
            f"${item.amount_mm:,.1f}MM",
            item.target_coupon_range,
            f"{item.target_duration:.1f}yr",
            f"{item.target_oas_bps:.0f}bps" if item.target_oas_bps > 0 else "—",
        )
        total += item.amount_mm

    t.add_section()
    t.add_row("", "[bold]TOTAL[/bold]", "", f"[bold green]${total:,.1f}MM[/bold green]",
              "", "", "")
    console.print(t)

    sc = state.selected_scenario
    mb = state.mbs_breakdown
    if sc:
        console.print(Panel(
            f"[bold]Selected Scenario:[/bold]   {sc.label}\n"
            f"[bold]MBS:[/bold]                 {sc.mbs_pct:.0f}%  (${sc.mbs_mm:,.1f}MM)\n"
            f"[bold]CMBS:[/bold]                {sc.cmbs_pct:.0f}%  (${sc.cmbs_mm:,.1f}MM)\n"
            f"[bold]Treasuries:[/bold]          {sc.treasury_pct:.0f}%  (${sc.treasury_mm:,.1f}MM)\n"
            f"[bold]Proj. Duration:[/bold]      {sc.projected_duration:.2f} years\n"
            f"[bold]Proj. Liquidity:[/bold]     {sc.projected_liquidity_score:.1f} / 10\n"
            f"[bold]Proj. Yield:[/bold]         {sc.projected_yield_pct:.2f}%",
            title="Portfolio Impact Summary",
            border_style="green",
        ))

    console.print("\n[bold]Options:[/bold]")
    console.print("  [cyan]C[/cyan]onfirm   — execute this purchase schedule")
    console.print("  [yellow]R[/yellow]evise    — go back to allocation (restart from Gate 3)")
    console.print("  [red]A[/red]bort     — cancel entire workflow\n")

    choice = await _prompt_choice("Final decision [C/R/A]: ", ["c", "r", "a"])

    status_map = {"c": ApprovalStatus.APPROVED, "r": ApprovalStatus.MODIFIED,
                  "a": ApprovalStatus.REJECTED}
    notes = ""
    if choice == "c":
        notes = (await _ainput("  Optional trade notes (press Enter to skip): ")).strip()

    return GateDecision(
        gate_name="final_approval",
        status=status_map[choice],
        trader_choice={"c": "confirm", "r": "revise", "a": "abort"}[choice],
        notes=notes,
    )
