# Fixed-Income Trading Workflow — Agentic AI System

An agentic, human-in-the-loop workflow for fixed-income portfolio management. Specialized AI agents collaborate to generate new-volume purchase schedules, assess portfolio risk, allocate across asset classes, and decompose MBS allocations — with a trader approval gate at every step.

Built on the **OpenAI Agents SDK**, with end-to-end observability via **Arize Phoenix**.

---

## Table of Contents

- [Key Features](#key-features)
- [Agentic Workflow](#agentic-workflow)
- [Code Structure](#code-structure)
- [Setup](#setup)
- [Running the Workflow](#running-the-workflow)
- [CLI Reference](#cli-reference)
- [CI/CD with Jenkins](#cicd-with-jenkins)
- [Observability](#observability)
- [Architecture Notes](#architecture-notes)

---

## Key Features

### Multi-Agent Orchestration
Four specialized agents are orchestrated sequentially. Each agent has a clearly defined role, a curated set of tools, and a plain-language skill definition. No agent makes decisions outside its scope.

### Human-in-the-Loop Gates (5 Gates)
Every major decision is paused for trader review. The trader can approve, modify parameters, select from options, or reject — before any downstream agent proceeds. The system never auto-advances past a gate without explicit approval.

### Skills-Based Agent Architecture
Agents are defined in Markdown files (`skills/*.md`) with YAML frontmatter specifying the model, tools, and instructions. Adding or modifying an agent requires no Python changes — only editing a `.md` file.

### Persistent Session State
Workflow state is persisted to JSON after every phase. If the session is interrupted (Ctrl+C), it can be resumed exactly where it left off using a session ID. A full gate audit trail is preserved.

### Rich CLI Interface
Interactive terminal panels rendered with [Rich](https://github.com/Textualize/rich): color-coded phase banners, formatted data tables, side-by-side scenario comparisons, and structured input prompts.

### End-to-End Tracing
All agent runs, tool calls, and model interactions are traced via [Arize Phoenix](https://phoenix.arize.com/) (OpenInference instrumentation). A local Phoenix server launches automatically with the workflow and is accessible in the browser.

### Realistic Synthetic Data
A data generator produces 34 fixed-income pools (MBS, CMBS, Treasuries) × 120 months of simulated market data — including CPR prepayments, CDR defaults, OAS, duration, convexity, and WAM/WALA seasoning — alongside an S-curve portfolio growth target.

---

## Agentic Workflow

```
uv run python main.py --appetite moderate --trader "Jane Smith"
```

```
┌─────────────────────────────────────────────────────────────────┐
│                     ORCHESTRATOR                                 │
│                                                                  │
│  Phase 1: NEW_VOLUME                                             │
│    NewVolumeAgent ──► compute new purchase volumes (12M + 10Y)  │
│    GATE 1 ──────────► Trader: Approve / Modify / Reject         │
│                                                                  │
│  Phase 2: RISK_ASSESSMENT                                        │
│    RiskAgent ────────► assess duration, liquidity, concentration │
│    GATE 2 ──────────► Trader: Confirm / Adjust bounds / Reject   │
│                                                                  │
│  Phase 3: ALLOCATION                                             │
│    AllocationAgent ──► generate 3 scenarios (C / M / A)         │
│    GATE 3 ──────────► Trader: Select scenario or enter custom %  │
│                                                                  │
│  Phase 4: MBS_DECOMPOSITION                                      │
│    MBSDecompositionAgent ► break MBS into agency sub-buckets    │
│    GATE 4 ──────────► Trader: Approve / Modify / Reject         │
│                                                                  │
│  Phase 5: FINAL_APPROVAL                                         │
│    GATE 5 ──────────► Trader: Confirm / Revise / Abort          │
│                         └─ Revise loops back to Phase 3          │
│                                                                  │
│  Output: Purchase schedule JSON + Gate audit trail               │
└─────────────────────────────────────────────────────────────────┘
```

### Agents and Responsibilities

| Agent | Role | Tools |
|---|---|---|
| **NewVolumeAgent** | Calculates monthly and annual new-purchase volumes needed to hit portfolio growth targets | `compute_new_volume_schedule`, `compute_volume_timing_analysis`, `summarise_pool_universe` |
| **RiskAgent** | Evaluates portfolio duration, liquidity, credit concentration, and OAS; establishes risk guardrails | `assess_portfolio_risk`, `estimate_duration_impact`, `get_risk_constraints_summary` |
| **AllocationAgent** | Generates three MBS/CMBS/Treasury allocation scenarios and explains trade-offs | `generate_allocation_scenarios`, `select_allocation_scenario`, `estimate_duration_impact` |
| **MBSDecompositionAgent** | Breaks the MBS allocation into FNMA/FHLMC/GNMA × fixed/ARM × 30YR/15YR sub-buckets; compiles the final purchase schedule | `decompose_mbs_allocation`, `build_purchase_schedule`, `estimate_duration_impact` |

### Gate Behavior

| Gate | Input to Trader | Trader Options |
|---|---|---|
| Gate 1 — New Volume | Monthly schedule + annual totals | Approve / Modify target $MM / Reject |
| Gate 2 — Risk Assessment | Duration bounds, liquidity floor, risk flags | Accept / Change bounds or risk appetite / Reject |
| Gate 3 — Allocation | Three scenarios side-by-side | Select 1–3 / Enter custom MBS/CMBS/TSY % / Reject |
| Gate 4 — MBS Decomposition | Agency sub-bucket breakdown table | Approve / Modify percentages / Reject |
| Gate 5 — Final Approval | Full 10-item purchase schedule | Confirm / Revise (→ Gate 3) / Abort |

---

## Code Structure

```
trading-workflow/
│
├── main.py                          # CLI entry point (argparse + async runner)
├── pyproject.toml                   # Project metadata, dependencies, and tool config (uv)
├── uv.lock                          # Locked dependency versions (auto-generated)
├── Jenkinsfile                      # Declarative CI/CD pipeline (lint → test → build → deploy)
├── .env.example                     # Environment variable template
├── .github/
│   ├── CONTRIBUTING.md              # Human-readable Python code standards
│   └── copilot-instructions.md     # Copilot code review rules (auto-applied)
│
├── models/
│   └── workflow_state.py            # Pydantic WorkflowState — single source of truth
│                                    # Enums: WorkflowPhase, RiskAppetite, ApprovalStatus
│                                    # Models: MonthlyVolume, RiskConstraints,
│                                    #         AllocationScenario, MBSBreakdown,
│                                    #         GateDecision, PurchaseScheduleItem
│
├── agents/                          # Thin agent builder wrappers (one-liners)
│   ├── new_volume_agent.py
│   ├── risk_agent.py
│   ├── allocation_agent.py
│   └── mbs_decomposition_agent.py
│
├── workflow_agents/
│   └── orchestrator.py              # TradingWorkflowOrchestrator — phase dispatch loop
│                                    # Runs agents, calls gates, saves state after each phase
│
├── skills/                          # Agent definitions as Markdown files
│   ├── new_volume_agent.md          # YAML frontmatter: name, model, tools list
│   ├── risk_agent.md                # Markdown body: plain-language instructions
│   ├── allocation_agent.md
│   ├── mbs_decomposition_agent.md
│   └── skill_loader.py             # SkillLoader: parses .md → resolves tools → builds Agent
│
├── tools/
│   ├── computation.py               # New-volume computation tools (function_tools)
│   ├── risk_tools.py                # Duration, liquidity, OAS risk tools
│   ├── allocation_tools.py          # Scenario generation, MBS decomposition, purchase schedule
│   ├── human_loop.py                # 5 async gate functions (Rich CLI panels + input)
│   └── tool_registry.py            # Singleton: tool name string → callable mapping
│
├── data/
│   └── sample_data.py               # Generates pool_df (34 pools × 120 months) + portfolio_df
│                                    # Models CPR/CDR runoff, OAS/duration drift, S-curve growth
│
├── persistence/
│   └── state_manager.py             # Async JSON persistence per session
│                                    # save(), load(), load_latest(), list_sessions()
│
├── tracing/
│   └── phoenix_setup.py             # Arize Phoenix local server + OTEL instrumentation
│
└── tests/
    ├── conftest.py                  # Shared pytest fixtures
    ├── unit/                        # Fast unit tests — no API calls
    │   ├── test_computation.py
    │   ├── test_risk_tools.py
    │   ├── test_allocation_tools.py
    │   └── test_workflow_state.py
    └── integration/                 # Full agent loop tests — require OPENAI_API_KEY
```

---

## Setup

### Prerequisites

- Python 3.10 or higher
- [uv](https://docs.astral.sh/uv/) — fast Python package and project manager
- An OpenAI API key

### 1. Install uv

**macOS / Linux**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell)**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

After installation, restart your terminal (or open a new shell) so the `uv` command is available on your PATH.

> Alternatively, uv can be installed via `pip install uv` or `brew install uv` (macOS with Homebrew).

---

### 2. Clone the repository

**macOS / Linux**
```bash
git clone <repo-url>
cd trading-workflow
```

**Windows (Command Prompt or PowerShell)**
```powershell
git clone <repo-url>
cd trading-workflow
```

---

### 3. Create the virtual environment and install dependencies

uv manages the virtual environment and resolves dependencies from `pyproject.toml` in a single step.

**macOS / Linux**
```bash
uv sync
```

**Windows**
```powershell
uv sync
```

This creates a `.venv` directory at the project root and installs all locked dependencies. A `uv.lock` file is generated (or updated) automatically — commit this file to ensure reproducible installs across machines.

> To install dependencies for a specific Python version:
> ```bash
> uv sync --python 3.12
> ```

---

### 4. Configure environment variables

**macOS / Linux**
```bash
cp .env.example .env
```

**Windows (Command Prompt)**
```cmd
copy .env.example .env
```

**Windows (PowerShell)**
```powershell
Copy-Item .env.example .env
```

Open `.env` in any text editor and fill in your values:

```env
OPENAI_API_KEY=sk-your-key-here
OPENAI_MODEL=gpt-4o                  # Model used by all agents
PHOENIX_HOST=127.0.0.1               # Arize Phoenix tracing server host
PHOENIX_PORT=6006                    # Arize Phoenix tracing server port
WORKFLOW_STATE_DIR=./workflow_states # Directory for session state files
```

---

## Running the Workflow

Use `uv run` to execute commands inside the managed virtual environment without manually activating it.

### Start a new workflow session

```bash
uv run python main.py --appetite moderate --trader "Jane Smith"
```

`--appetite` sets the default risk posture — agents and allocation templates will calibrate to this. Valid values: `conservative`, `moderate`, `aggressive`.

### Resume a saved session

```bash
# Resume the most recent session
uv run python main.py --resume latest

# Resume a specific session by ID
uv run python main.py --resume 20240315_143022_a3f9b1
```

### List all saved sessions

```bash
uv run python main.py --list
```

### Preview the sample data (without running the workflow)

```bash
uv run python main.py --preview-data
```

### Run without tracing (no Phoenix server)

```bash
uv run python main.py --appetite moderate --trader "Jane Smith" --no-tracing
```

### Optional: activate the virtual environment directly

If you prefer to activate the environment once and use `python` directly:

**macOS / Linux**
```bash
source .venv/bin/activate
python main.py --appetite moderate --trader "Jane Smith"
```

**Windows (Command Prompt)**
```cmd
.venv\Scripts\activate.bat
python main.py --appetite moderate --trader "Jane Smith"
```

**Windows (PowerShell)**
```powershell
.venv\Scripts\Activate.ps1
python main.py --appetite moderate --trader "Jane Smith"
```

---

## CLI Reference

| Flag | Type | Default | Description |
|---|---|---|---|
| `--appetite` | `conservative` \| `moderate` \| `aggressive` | `moderate` | Risk appetite for the session |
| `--trader` | string | `Trader` | Trader display name shown in gates |
| `--resume` | session ID or `latest` | — | Resume a paused session |
| `--list` | flag | — | Print a table of all saved sessions and exit |
| `--preview-data` | flag | — | Display sample pool/portfolio data and exit |
| `--no-tracing` | flag | — | Disable Arize Phoenix tracing |
| `--state-dir` | path | `./workflow_states` | Directory for session JSON files |

---

## CI/CD with Jenkins

### Pipeline Overview

The `Jenkinsfile` at the project root defines a declarative pipeline with six stages:

| Stage | What it does |
|---|---|
| **Checkout** | Checks out source from SCM |
| **Install uv** | Installs uv if not already present on the agent |
| **Install Dependencies** | Runs `uv sync --all-groups --frozen` to install runtime + dev dependencies from the lock file |
| **Lint** | Runs `ruff format --check` and `ruff check` — fails fast on any formatting or style violation |
| **Type Check** | Runs `mypy` across all source modules |
| **Test** | Runs `pytest tests/unit` with JUnit XML and HTML coverage reports; enforces 70% minimum coverage |
| **Build** | Runs `uv build` to produce a `.whl` and `.tar.gz` in `dist/`; archives artifacts |
| **Deploy** | Runs only on the `main` branch — install the built wheel to a target environment (configure one of the commented options in the `Jenkinsfile`) |

The pipeline is cross-platform and runs correctly on both Linux and Windows Jenkins agents.

### Jenkins Setup

**1. Required credentials**

Add the following in Jenkins → Manage Jenkins → Credentials:

| ID | Type | Description |
|---|---|---|
| `openai-api-key` | Secret text | OpenAI API key used by agents |

**2. Create the pipeline job**

- New Item → Pipeline
- Under **Pipeline**, set **Definition** to `Pipeline script from SCM`
- Point SCM to this repository and set **Script Path** to `Jenkinsfile`

**3. Enable multibranch (recommended)**

Use a **Multibranch Pipeline** job to automatically detect branches and pull requests. The `Deploy` stage is gated to run only on `main`.

### Running quality checks locally

Before pushing, run the same checks the pipeline executes:

```bash
# Lint
uv run ruff format --check .
uv run ruff check .

# Auto-fix lint issues
uv run ruff format .
uv run ruff check . --fix

# Type check
uv run mypy .

# Unit tests with coverage
uv run pytest tests/unit --cov --cov-report=term-missing
```

### Test structure

```
tests/
├── conftest.py              # Shared fixtures (sample pool/portfolio JSON)
├── unit/                    # Fast tests — no API calls, no I/O
│   ├── test_computation.py  # NewVolumeAgent tools
│   ├── test_risk_tools.py   # RiskAgent tools
│   ├── test_allocation_tools.py  # AllocationAgent + MBS decomposition tools
│   └── test_workflow_state.py    # WorkflowState model, phase transitions, serialization
└── integration/             # Full agent loop tests — require OPENAI_API_KEY
```

Unit tests run in CI on every push. Integration tests require a live API key and should be run manually or in a separate nightly job.

---

## Observability

When tracing is enabled (default), a local Arize Phoenix server starts automatically. Open the UI at:

```
http://127.0.0.1:6006
```

The following are instrumented automatically:

- **Agent runs** — each agent's full execution trace (prompt, model, response)
- **Tool calls** — inputs and outputs for every function_tool invocation
- **Raw model calls** — token usage, latency, streaming behavior

Traces are organized by session and phase, making it straightforward to debug agent reasoning, inspect tool call chains, and measure latency across gates.

---

## Architecture Notes

### Skills System
Each agent is fully described by a single `.md` file in `skills/`. The YAML frontmatter declares the agent's name, model, and tools; the Markdown body contains the plain-language instructions passed to the model. `SkillLoader` parses this file, resolves tool callables from `ToolRegistry`, and returns a ready-to-use `Agent` object. This means agent behavior can be tuned — or a new agent created — without touching Python code.

### State as Single Source of Truth
`WorkflowState` (Pydantic model) is the canonical representation of a session. Every agent output, gate decision, and phase transition is recorded on this object before it is persisted. The orchestrator reads from and writes to state exclusively — agents and tools do not share any other mutable state.

### Separation of Concerns
- **Agents** are responsible only for reasoning and producing structured output.
- **Tools** are pure functions — deterministic given their inputs, no side effects on global state.
- **Gates** are responsible for presenting information to the trader and capturing decisions.
- **Orchestrator** is responsible for sequencing, branching, and persisting state.

### Phase Branching
The orchestrator supports non-linear flows. A `REJECT` at any gate terminates the workflow cleanly. A `MODIFIED` response at Gate 5 loops back to Phase 3 (Allocation), allowing the trader to revise the scenario selection and regenerate the MBS decomposition and purchase schedule without rerunning the risk assessment.
