"""
Trading Workflow CLI Entry Point

Usage:
  python main.py                          # Start a new workflow (moderate appetite)
  python main.py --appetite aggressive    # New workflow with aggressive appetite
  python main.py --resume <session_id>    # Resume a saved session
  python main.py --resume latest          # Resume the most recent session
  python main.py --list                   # List all saved sessions
  python main.py --preview-data           # Preview the sample DataFrame
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

# Force UTF-8 on Windows terminals before any Rich output
if sys.platform == "win32":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")

from dotenv import load_dotenv
from rich.console import Console
from rich.table import Table

load_dotenv()

# Validate OPENAI_API_KEY early
if not os.getenv("OPENAI_API_KEY"):
    print("ERROR: OPENAI_API_KEY not set. Copy .env.example to .env and add your key.")
    sys.exit(1)

from models.workflow_state import RiskAppetite
from persistence.state_manager import StateManager
from tracing.phoenix_setup import setup_tracing

logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logging.getLogger("trading_workflow").setLevel(logging.DEBUG)

console = Console(legacy_windows=False)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Fixed-Income Agentic Trading Workflow",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--appetite",
        choices=["conservative", "moderate", "aggressive"],
        default="moderate",
        help="Trader risk appetite (default: moderate)",
    )
    p.add_argument(
        "--trader",
        default="Trader",
        help="Trader display name",
    )
    p.add_argument(
        "--resume",
        metavar="SESSION_ID",
        help="Resume a saved session. Use 'latest' for most recent.",
    )
    p.add_argument(
        "--list",
        action="store_true",
        help="List all saved sessions",
    )
    p.add_argument(
        "--preview-data",
        action="store_true",
        help="Preview the sample DataFrame and exit",
    )
    p.add_argument(
        "--no-tracing",
        action="store_true",
        help="Disable Arize Phoenix tracing (useful offline)",
    )
    p.add_argument(
        "--state-dir",
        default=os.getenv("WORKFLOW_STATE_DIR", "./workflow_states"),
        help="Directory for persisted workflow states",
    )
    return p.parse_args()


# ---------------------------------------------------------------------------
# Sub-commands
# ---------------------------------------------------------------------------

def cmd_list_sessions(state_dir: str) -> None:
    sm = StateManager(state_dir)
    sessions = sm.list_sessions()
    if not sessions:
        console.print("[yellow]No saved sessions found.[/yellow]")
        return

    t = Table(title="Saved Workflow Sessions", show_lines=True)
    t.add_column("Session ID",   style="cyan", width=32)
    t.add_column("Phase",        width=20)
    t.add_column("Trader",       width=14)
    t.add_column("Last Updated", width=22)

    for s in sorted(sessions, key=lambda x: x.get("updated_at", ""), reverse=True):
        t.add_row(
            s.get("session_id", "?"),
            s.get("phase", "?"),
            s.get("trader_name", "?"),
            s.get("updated_at", "?")[:19],
        )
    console.print(t)


def cmd_preview_data() -> None:
    from data.sample_data import generate_sample_data

    console.print("[cyan]Generating sample data...[/cyan]")
    pool_df, portfolio_df = generate_sample_data()

    console.print(f"\n[bold]Pool Universe[/bold]  ({pool_df.shape[0]:,} rows × {pool_df.shape[1]} cols)")
    console.print(f"  CUSIPs: {pool_df['cusip'].nunique()}")

    # Product type breakdown
    for pt in pool_df["product_type"].unique():
        sub = pool_df[pool_df["product_type"] == pt]
        console.print(f"  {pt}: {sub['cusip'].nunique()} pools")

    # Sample rows
    console.print("\n[bold]First 5 rows (pool_universe_df):[/bold]")
    console.print(pool_df.head().to_string())

    console.print("\n[bold]Portfolio Projections (first 12 months):[/bold]")
    console.print(portfolio_df.head(12).to_string(index=False))

    console.print("\n[bold]Portfolio Projections (last 12 months):[/bold]")
    console.print(portfolio_df.tail(12).to_string(index=False))

    console.print(f"\n[bold]Columns in pool_universe_df:[/bold]")
    for col in pool_df.columns:
        console.print(f"  {col}: {pool_df[col].dtype}")


# ---------------------------------------------------------------------------
# Main async runner
# ---------------------------------------------------------------------------

async def main_async(args: argparse.Namespace) -> None:
    # ── Setup tracing ────────────────────────────────────────────────────────
    if not args.no_tracing:
        console.print("[dim]Setting up Arize Phoenix tracing...[/dim]")
        try:
            setup_tracing(
                project_name="trading-workflow",
                launch_local=True,
            )
            console.print(
                "[dim]Phoenix UI: http://127.0.0.1:6006  "
                "(open in browser to view LLM traces)[/dim]\n"
            )
        except Exception as e:
            console.print(f"[yellow]Tracing setup failed (continuing without): {e}[/yellow]")
    else:
        console.print("[dim]Tracing disabled.[/dim]\n")

    from workflow_agents.orchestrator import TradingWorkflowOrchestrator

    sm           = StateManager(args.state_dir)
    orchestrator = TradingWorkflowOrchestrator(state_manager=sm)

    # ── Resolve resume ────────────────────────────────────────────────────────
    resume_id: str | None = None
    if args.resume:
        if args.resume == "latest":
            latest = await sm.load_latest()
            if latest is None:
                console.print("[red]No saved sessions found.[/red]")
                return
            resume_id = latest.session_id
        else:
            resume_id = args.resume

    # ── Run ──────────────────────────────────────────────────────────────────
    await orchestrator.run(
        resume_session_id=resume_id,
        trader_name=args.trader,
        risk_appetite=RiskAppetite(args.appetite),
    )


def main() -> None:
    args = parse_args()

    if args.list:
        cmd_list_sessions(args.state_dir)
        return

    if args.preview_data:
        cmd_preview_data()
        return

    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
