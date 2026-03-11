# Python Code Standards

This document defines the coding standards and conventions for this project. All contributors are expected to follow these guidelines to maintain consistency, readability, and long-term maintainability.

---

## Table of Contents

- [Language and Runtime](#language-and-runtime)
- [Formatting](#formatting)
- [Naming Conventions](#naming-conventions)
- [Type Annotations](#type-annotations)
- [Imports](#imports)
- [Docstrings](#docstrings)
- [Comments](#comments)
- [Error Handling](#error-handling)
- [Async Code](#async-code)
- [Pydantic Models](#pydantic-models)
- [Agent and Tool Authoring](#agent-and-tool-authoring)
- [File and Module Organization](#file-and-module-organization)
- [Testing](#testing)
- [Dependencies](#dependencies)
- [What to Avoid](#what-to-avoid)

---

## Language and Runtime

- **Python 3.10+** is required. Use modern language features where they improve clarity.
- Use `match` / `case` (structural pattern matching) for branching on enum values or tagged unions.
- Use `X | Y` union syntax for type hints instead of `Union[X, Y]`.
- Use `X | None` instead of `Optional[X]`.

---

## Formatting

This project uses **[Ruff](https://docs.astral.sh/ruff/)** for both formatting and linting. Do not introduce manual formatting that conflicts with Ruff's output.

| Rule | Value |
|---|---|
| Line length | 100 characters |
| Indentation | 4 spaces (no tabs) |
| Quotes | Double quotes `"` |
| Trailing commas | Required in multi-line collections |

### Run the formatter before committing

```bash
uv run ruff format .
uv run ruff check . --fix
```

---

## Naming Conventions

| Construct | Convention | Example |
|---|---|---|
| Variables | `snake_case` | `new_volume_mm` |
| Functions | `snake_case` | `compute_new_volume_schedule` |
| Async functions | `snake_case` | `async def gate_risk_assessment` |
| Classes | `PascalCase` | `WorkflowState`, `TradingWorkflowOrchestrator` |
| Pydantic models | `PascalCase` | `AllocationScenario`, `GateDecision` |
| Constants | `UPPER_SNAKE_CASE` | `DEFAULT_RISK_APPETITE` |
| Enums | `PascalCase` class, `UPPER_SNAKE_CASE` members | `WorkflowPhase.RISK_ASSESSMENT` |
| Private methods | Leading underscore | `_dispatch_phase`, `_build_pool_summary` |
| Module files | `snake_case` | `risk_tools.py`, `state_manager.py` |

Names should be descriptive and unambiguous. Avoid single-letter names outside of short loop indices or mathematical expressions. Avoid abbreviations unless they are standard domain terms (e.g., `oas`, `wam`, `cpr`, `mbs`).

---

## Type Annotations

All functions and methods must have complete type annotations — both parameters and return types.

```python
# Good
def compute_new_volume_schedule(
    portfolio_df: pd.DataFrame,
    target_months: int = 12,
) -> dict[str, float]:
    ...

# Bad — missing annotations
def compute_new_volume_schedule(portfolio_df, target_months=12):
    ...
```

- Use `dict[str, float]` not `Dict[str, float]` (no need to import from `typing` for built-in generics in Python 3.10+).
- Use `list[str]` not `List[str]`.
- Use `tuple[int, str]` not `Tuple[int, str]`.
- Use `X | None` not `Optional[X]`.
- Annotate class attributes explicitly when not using Pydantic.

---

## Imports

Imports must be ordered and grouped as follows (enforced by Ruff):

1. Standard library
2. Third-party packages
3. Local modules

Each group is separated by a blank line. Within each group, imports are sorted alphabetically.

```python
# Standard library
import asyncio
import json
from pathlib import Path

# Third-party
import pandas as pd
from pydantic import BaseModel
from rich.panel import Panel

# Local
from models.workflow_state import WorkflowState
from tools.computation import compute_new_volume_schedule
```

- Prefer `from module import name` over `import module` when importing a specific object.
- Never use wildcard imports (`from module import *`).
- Never import inside functions unless necessary to avoid circular imports; if so, add a comment explaining why.

---

## Docstrings

All public modules, classes, and functions must have docstrings. Use the **Google style**.

### Module docstring

```python
"""Tools for computing new-volume purchase schedules.

Provides function_tools for the NewVolumeAgent: schedule computation,
pool universe summarization, and timing urgency analysis.
"""
```

### Function docstring

```python
def assess_portfolio_risk(pool_summary_json: str, risk_appetite: str) -> str:
    """Evaluate portfolio risk across duration, liquidity, and concentration dimensions.

    Args:
        pool_summary_json: JSON string of aggregated pool statistics by product type.
        risk_appetite: One of 'conservative', 'moderate', or 'aggressive'.

    Returns:
        JSON string containing risk flags, computed constraints, and a plain-language summary.

    Raises:
        ValueError: If risk_appetite is not a recognized value.
    """
```

### Class docstring

```python
class TradingWorkflowOrchestrator:
    """Orchestrates the end-to-end agentic trading workflow.

    Manages phase sequencing, agent execution, gate approval, and state
    persistence. Each phase is dispatched by _dispatch_phase() and the
    workflow loop continues until WorkflowPhase.COMPLETE is reached.
    """
```

Private methods and one-liner helper functions used only internally do not require docstrings, but should have an inline comment if the logic is non-obvious.

---

## Comments

- Write comments to explain **why**, not **what**. The code itself should make the "what" obvious.
- Comments must be complete sentences with correct grammar and punctuation.
- Keep comments up to date. A wrong comment is worse than no comment.

```python
# Good — explains intent
# Run in executor to avoid blocking the event loop while waiting for terminal input.
response = await loop.run_in_executor(None, input, prompt)

# Bad — restates the code
# Call input()
response = await loop.run_in_executor(None, input, prompt)
```

- Use `# TODO: <description>` for known gaps. Include a brief explanation of what is missing and why.
- Do not leave commented-out code in the codebase. Delete it and rely on git history.

---

## Error Handling

- Catch specific exceptions, not bare `except:` or `except Exception:` unless at a top-level boundary.
- Always include a meaningful error message.
- In async gate functions, validate trader input and re-prompt rather than raising exceptions to the orchestrator.

```python
# Good
try:
    state = await state_manager.load(session_id)
except FileNotFoundError:
    raise ValueError(f"Session '{session_id}' not found in {state_dir}.")

# Bad
try:
    state = await state_manager.load(session_id)
except:
    pass
```

- Do not use exceptions for control flow. Use `if` conditions and early returns instead.
- Log or surface errors to the user via Rich output before re-raising, so the trader can understand what went wrong.

---

## Async Code

This project is fully async. Follow these conventions:

- All I/O-bound operations (file reads, user input, agent runs) must be `async`.
- Use `asyncio.run()` only at the top-level entry point (`main.py`). Everywhere else, `await` directly.
- Use `aiofiles` for file I/O. Do not use synchronous `open()` inside async functions.
- Use `await loop.run_in_executor(None, ...)` to call blocking synchronous code (e.g., `input()`) from an async context.
- Never use `time.sleep()` inside async code. Use `await asyncio.sleep()` if a delay is needed.
- Prefix all coroutine functions with `async def`. Do not define a function as `async` unless it uses `await`.

```python
# Good
async def save(self, state: WorkflowState) -> None:
    async with aiofiles.open(path, "w") as f:
        await f.write(state.model_dump_json(indent=2))

# Bad — blocking I/O inside async function
async def save(self, state: WorkflowState) -> None:
    with open(path, "w") as f:
        f.write(state.model_dump_json(indent=2))
```

---

## Pydantic Models

- All structured data that crosses a module boundary must be a Pydantic `BaseModel`.
- Use `model_dump_json()` / `model_validate_json()` for serialization — not `dict()` or `json.dumps()`.
- Define field defaults using `Field(default=...)` for documentation clarity.
- Use `model_config = ConfigDict(...)` for model-level configuration (not the deprecated `class Config`).
- Enums used as field types must subclass both the value type and `enum.Enum` (e.g., `class WorkflowPhase(str, enum.Enum)`).
- Do not add business logic to Pydantic models beyond simple validation and convenience methods. Keep heavy computation in `tools/`.

```python
from pydantic import BaseModel, Field

class RiskConstraints(BaseModel):
    min_duration: float = Field(default=4.0, description="Minimum portfolio duration in years.")
    max_duration: float = Field(default=7.0, description="Maximum portfolio duration in years.")
    min_liquidity_score: float = Field(default=6.0, description="Minimum blended liquidity score (1–10).")
```

---

## Agent and Tool Authoring

### Tools (`tools/*.py`)

- Every tool exposed to an agent must be decorated with `@function_tool`.
- Tools must be **pure functions**: given the same inputs, they return the same output with no side effects on shared state.
- Tool inputs and outputs must be JSON-serializable. Use `str` for complex payloads (serialize to/from JSON inside the tool).
- Tool docstrings are passed directly to the model as tool descriptions — write them clearly and from the model's perspective.
- Register every new tool in `tools/tool_registry.py` so it can be referenced by name in skill `.md` files.

### Skills (`skills/*.md`)

- Every agent must have a corresponding `.md` file in `skills/`.
- The YAML frontmatter must include `name`, `display_name`, `model`, and `tools` (list of registered tool names).
- Instructions in the Markdown body must be written in plain English, scoped to the agent's role.
- Do not instruct an agent to make decisions that belong to a different agent or to a human gate.

### Agent builders (`agents/*.py`)

- Agent builder files should be one-liners: `return SkillLoader.load("skill_name").build()`.
- Do not inline agent instructions or tool lists in Python — keep everything in the `.md` file.

---

## File and Module Organization

- One class per file for major domain classes (e.g., `WorkflowState`, `TradingWorkflowOrchestrator`).
- Group related function_tools in the same `tools/` file by agent affinity.
- Keep `main.py` thin: argument parsing, environment validation, and calling into `orchestrator.run()`. No business logic.
- Do not create utility modules for single-use helpers. Inline simple logic at the call site.
- All new top-level modules must have a module-level docstring.

---

## Testing

- Place tests under a `tests/` directory mirroring the source layout (e.g., `tests/tools/test_computation.py`).
- Use `pytest` as the test runner.
- Run tests with:

```bash
uv run pytest
```

- Unit tests for tools must not call the OpenAI API. Use static inputs and assert on output structure/values.
- Gate functions that require terminal input should be tested with mocked `input()` via `unittest.mock.patch`.
- Integration tests that run full agent loops should be placed in `tests/integration/` and clearly marked so they can be excluded from CI when no API key is available.
- Each public function in `tools/` should have at least one happy-path test and one edge-case test.

---

## Dependencies

- All dependencies are declared in `pyproject.toml` and locked in `uv.lock`.
- Add a new dependency with:

```bash
uv add <package>
```

- Add a development-only dependency (e.g., linters, test frameworks) with:

```bash
uv add --dev <package>
```

- Do not edit `uv.lock` manually. Do not add packages to `requirements.txt` — it is no longer the source of truth.
- Pin to a minimum version (`>=x.y.z`) rather than an exact version unless a specific version is strictly required.
- Before adding a new dependency, check whether the functionality can be achieved with the standard library or an already-present package.

---

## What to Avoid

| Practice | Reason |
|---|---|
| `from module import *` | Pollutes the namespace; makes dependencies invisible |
| Bare `except:` clauses | Swallows unexpected errors silently |
| Synchronous file I/O inside async functions | Blocks the event loop |
| Business logic in `main.py` | Harder to test; breaks separation of concerns |
| Hardcoded secrets or API keys | Security risk; use `.env` and `python-dotenv` |
| Inline agent instructions in Python | Makes agent behavior harder to iterate on |
| Mutating global state in tools | Breaks tool purity; causes subtle bugs with agent re-use |
| Commented-out code | Creates noise; use git history instead |
| `print()` for user-facing output | Use `rich.console.Console` for formatted output |
| `time.sleep()` in async code | Blocks the event loop; use `asyncio.sleep()` |
