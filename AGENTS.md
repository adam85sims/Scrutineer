# Agent Instructions

## Repository boundaries

- The main package is `src/sentinel/` and is tested by `tests/`; its public entrypoints are `sentinel` / `sentinel-run` (CLI) and `sentinel.__init__`. The WebUI is `sentinel serve` (entrypoint `sentinel-serve`) and lives at `src/sentinel/web/`.
- `pattern-memory/` is a separate Python package with its own `pyproject.toml`, dependencies, CLI, and test suite. Install and test it from that directory; root installs do not cover it.
- Framework adapters, OpenTelemetry support, and the WebUI are optional dependencies. Do not add hard imports for them to core code.

## Main package commands

- Requires Python 3.11+. Set up the development environment with `pip install -e ".[dev]"`; add `.[langchain]`, `.[crewai]`, `.[openai]`, `.[otel]`, `.[governance]`, `.[web]`, or `.[all]` when needed.
- Run the root suite with `python -m pytest tests/ -v`; target a file or test with the same command followed by its path and/or `-k expression`. The `[dev]` extra now includes `pytest-asyncio`, `pytest-xdist`, `pytest-randomly`, `pytest-playwright`, and `httpx`, so parallel/order-independence/E2E tests work out of the box.
- Run the LangChain integration file with `pip install -e ".[langchain]"` followed by `python -m pytest tests/sentinel/test_integration_langchain.py -v`. It uses deterministic simulated agent loops and skips when `langchain-core` is absent; it does not require an LLM API.
- Run lint with `ruff check src/ tests/`. Ruff is configured for Python 3.11, 100-character lines, and rules `E,F,W,I,UP`.
- For testing rules (parallel-safety, no-shared-state, conftest helpers, recommended local commands) see `tests/AGENTS.md` — it is the source of truth for anything under `tests/`.

## WebUI

- Start with `sentinel serve` (or `sentinel-serve`); default `http://127.0.0.1:8080`. FastAPI app factory is at `sentinel.web.app:create_app`.
- Requires `pip install -e ".[web]"`. The WebUI ships pre-populated demo data under `.sentinel/runs/` and `.sentinel/baselines/` so first-run users see populated lists; regenerate with `python scripts/generate_demo_data.py`.
- Browser E2E tests live in `tests/sentinel/web/test_playwright_e2e.py` and require `pip install -e ".[dev]"` plus `playwright install chromium`. They are marked `e2e`; deselect with `-m "not e2e"` when not available.

## CLI and scenarios

- `sentinel run` requires exactly one of `--scenario NAME`, `--all`, or `--path FILE`; use `sentinel run --path examples/basic_scenario.yaml` for a file scenario.
- YAML scenario loading requires PyYAML (`.[governance]`); JSON scenarios do not. Baseline/report commands operate on persisted results and can create local report artifacts.
- `click` is a core dependency (`click>=8.0`) — required by `sentinel`, `sentinel-run`, and `sentinel-serve` entrypoints.

## Pattern-memory commands

- From `pattern-memory/`, install with `pip install -e ".[dev]"` and run `python3 -m pytest tests/ -v`.
- Its runtime uses SQLite plus ChromaDB and exposes `pattern-memory` and `pattern-memory-server`; avoid assuming its top-level modules belong to the `sentinel` package.

## Working notes (2026-10-08)

- **Verify in an environment that matches CI, not your dev venv.** A dev venv carrying
  hand-installed extras can hide a CI-only failure: the `test` job was red for weeks because
  `pip install -e ".[all,dev]"` could not import `fastapi` at all. Reproduce before trusting a
  green: `uv venv --python 3.11 /tmp/check && uv pip install -e ".[all,dev]"`.
- **The `[all]` extra must stay in sync with the extras above it.** It is commented
  "# Everything" and previously omitted the four `[web]` deps, which silently SKIPPED the 25
  WebUI API tests (they guard with `importorskip`) and turned the e2e module into a
  collection error that aborted the entire run.
- **Never remove `-m "not e2e"` from the `test` job.** Playwright's sync fixtures keep an
  asyncio loop alive, and co-running that module with the suite's `@pytest.mark.asyncio` test
  raises "Runner.run() cannot be called from a running event loop". Browser e2e has its own
  job that installs chromium. Note also that a collection error bypasses marker filters
  entirely — `-m` cannot rescue a module whose import fails — so guard every optional
  module-level import with `pytest.importorskip`.
- **After moving the project, rebuild `.venv`.** Pip's shebangs hold the absolute path the
  venv was created at, so a moved checkout gives "bad interpreter: No such file or directory".
  Rebuild with `uv venv --python 3.11 .venv` then
  `uv pip install -e ".[dev,web,governance,adapters]"`.
- **The distribution name is PROVISIONAL.** `pyproject.toml` says `sentinel-agents` pending
  the brand decision (see `TODO.md` → Blocked). Do not publish to PyPI before that is settled.
- **Chaos in scenario files:** `tool_failure`, `network_partition`, `clock_skew` and
  `memory_pressure` are reachable from YAML, and each needs a target (`tool: <name>`).
  `context_degradation`, `spec_drift` and `cascading_failures` are refused *on purpose*: they
  are step-driven and need a real agent (readiness §4.4). Do not "fix" that by wiring them to
  the scripted reference agent — it has no context to degrade, so the result would be theatre.
- **Adapter rule:** an adapter that cannot intercept must raise, never delegate. Failing open
  runs the customer's real tools while reporting success — see
  `sentinel/adapters/langchain.py` (`AgentInterceptionError`) and `TODO.md` for the OpenAI
  adapter, which still has the old behaviour.