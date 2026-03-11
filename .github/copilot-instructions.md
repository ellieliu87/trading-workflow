# Copilot Instructions — Fixed-Income Trading Workflow

These instructions apply to all code suggestions, completions, and pull request reviews in this repository.

---

## Language and Syntax

- Target Python 3.10+. Use `match`/`case` for enum branching, `X | Y` for union types, `X | None` instead of `Optional[X]`, and built-in generics (`list[str]`, `dict[str, float]`, `tuple[int, str]`) instead of `typing` equivalents.

## Formatting

- Line length: 100 characters maximum.
- Indentation: 4 spaces. No tabs.
- Strings: double quotes.
- Multi-line collections must have a trailing comma on the last item.
- Formatting is enforced by Ruff (`uv run ruff format .` / `uv run ruff check . --fix`). Do not suggest style that conflicts with Ruff defaults.

## Naming

- Variables and functions: `snake_case`.
- Classes and Pydantic models: `PascalCase`.
- Constants and enum members: `UPPER_SNAKE_CASE`.
- Private methods and attributes: leading underscore (e.g., `_dispatch_phase`).
- Names must be descriptive. No single-letter names outside loop indices or math. Standard domain abbreviations are acceptable (`oas`, `wam`, `cpr`, `mbs`, `cmbs`, `tsy`).

## Type Annotations

- Every function and method must have fully annotated parameters and return type. Flag any unannotated public function as a review issue.
- Use `-> None` explicitly when a function returns nothing.

## Imports

- Order: standard library → third-party → local, each group separated by a blank line.
- No wildcard imports (`from module import *`).
- No imports inside functions unless required to break a circular import (must include a comment explaining why).

## Docstrings

- All public modules, classes, and functions must have a Google-style docstring.
- Function docstrings must document `Args:`, `Returns:`, and `Raises:` where applicable.
- Flag any public function or class missing a docstring.

## Comments

- Comments explain *why*, not *what*. Flag comments that merely restate the code.
- No commented-out code. Delete unused code and rely on git history.
- TODOs must include a brief explanation: `# TODO: <what and why>`.

## Error Handling

- No bare `except:` or `except Exception:` unless at a top-level boundary with explicit logging.
- Catch the most specific exception type available.
- Do not use exceptions for control flow. Use `if` conditions and early returns.

## Async

- All I/O-bound operations must be `async`/`await`. Flag synchronous file I/O (`open()`) inside async functions — use `aiofiles` instead.
- `asyncio.run()` is only permitted in `main.py`. Everywhere else, use `await` directly.
- No `time.sleep()` in async code. Use `await asyncio.sleep()`.
- Blocking calls (e.g., `input()`) must be wrapped with `await loop.run_in_executor(None, ...)`.
- Only define a function as `async` if it contains at least one `await`.

## Pydantic Models

- All structured cross-module data must be a `BaseModel`.
- Use `model_dump_json()` and `model_validate_json()` for serialization — not `dict()` or `json.dumps()`.
- Use `Field(default=..., description=...)` for all fields.
- Use `model_config = ConfigDict(...)` — not the deprecated inner `class Config`.
- Enums must subclass both the value type and `enum.Enum` (e.g., `class WorkflowPhase(str, enum.Enum)`).
- No heavy business logic in models. Keep computation in `tools/`.

## Tools (`tools/*.py`)

- Every agent-facing tool must be decorated with `@function_tool`.
- Tools must be pure functions: no side effects, no mutation of shared state.
- All inputs and outputs must be JSON-serializable. Use `str` for complex payloads.
- Tool docstrings are sent to the model — write them clearly and from the model's perspective.
- Every new tool must be registered in `tools/tool_registry.py`.

## Agent and Skill Authoring

- Agent builder files (`agents/*.py`) must be one-liners: `return SkillLoader.load("skill_name").build()`. Flag any agent file that inlines instructions or tool lists.
- Agent instructions belong in `skills/<agent_name>.md` — not in Python code.
- Skill `.md` frontmatter must include `name`, `display_name`, `model`, and `tools`.

## Module Organization

- `main.py` must stay thin: argument parsing, environment validation, entry into `orchestrator.run()`. Flag business logic added to `main.py`.
- One major class per file.
- No utility modules created for single-use helpers. Inline simple logic.
- Every new top-level module must have a module-level docstring.

## Dependencies

- Dependencies are managed via `uv`. New packages are added with `uv add <package>` (or `uv add --dev` for dev tools).
- Do not suggest edits to `uv.lock` or adding packages to `requirements.txt`.
- Prefer standard library or already-present packages before adding new dependencies.

## Security

- No hardcoded secrets, API keys, or credentials. All secrets must be loaded from `.env` via `python-dotenv`.
- Flag any string literal that resembles a key, token, or password.

## What to Flag in Review

Flag the following as review issues:

- Unannotated public functions or methods
- Missing docstrings on public modules, classes, or functions
- Bare `except:` clauses
- `time.sleep()` inside async functions
- Synchronous file I/O inside async functions
- Wildcard imports
- Hardcoded secrets or API keys
- Business logic added to `main.py`
- Agent builder files with inlined instructions or tool definitions
- Commented-out code blocks
- `Optional[X]` or `typing.List` / `typing.Dict` instead of modern syntax
