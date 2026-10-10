# Scrutineer

**Agent Behavioral Testing Platform** — Tests what agents DO, not just what they SAY.

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-647%20passing-brightgreen.svg)](#testing)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-red.svg)](https://docs.astral.sh/ruff/)

## The Problem

Most AI projects do not survive contact with production. RAND's analysis of AI project
failures — 65 interviews with experienced AI/ML engineers — cites estimates that
**more than 80% of AI projects fail: twice the rate of non-AI IT projects** ([RAND RR-A2680-1, 2024](https://www.rand.org/pubs/research_reports/RRA2680-1.html)).
PwC's study of 1,217 senior executives puts the same gap in financial terms: **74% of
AI's economic value is captured by just 20% of organisations**, and "many companies are
busy rolling out AI pilots, but only a minority are converting that activity into
measurable financial returns" ([PwC AI Performance Study, 2026](https://www.pwc.com/gx/en/news-room/press-releases/2026/pwc-2026-ai-performance-study.html)).

Yet the entire evaluation ecosystem (DeepEval, LangSmith, MS AGT) focuses on
output quality or observability. Nobody tests agent **behavior** in production-like
environments before deployment.

## The Solution

Scrutineer fills that gap. It's a behavioral testing platform that:

1. **Mocks your agent's environment** — tools, APIs, databases with configurable
   latency, errors, and rate limits
2. **Injects chaos** — tool failures, context degradation, cascading errors,
   spec drift under pressure
3. **Asserts behavior** — 20+ assertions across tool calls, state consistency,
   governance compliance, resilience, and performance
4. **Reports regressions** — structural diffing, baseline comparison, HTML + JUnit reports

## Quick Start

> **Distribution name:** this project publishes to PyPI as **`scrutineer-agents`**.
> Do **not** run `pip install scrutineer` — that name belongs to an unrelated project and
> installs a different library. The import package and the console script are both
> `scrutineer`.

```bash
# Dependencies are click + pyyaml; the WebUI and the framework adapters are extras.
pip install scrutineer-agents

# Write the starter kit into ./scrutineer-examples
scrutineer init

# A scenario that passes
scrutineer run --path scrutineer-examples/basic_scenario.yaml

# Its negative control — the same chaos with an agent that has no fallback.
# FAILS on purpose: a scenario that cannot fail cannot tell you anything.
scrutineer run --path scrutineer-examples/chaos_scenario_unhandled.yaml
```

Extras — install only what you use:

```bash
pip install "scrutineer-agents[web]"        # FastAPI dashboard: scrutineer serve
pip install "scrutineer-agents[adapters]"   # langchain-core, crewai, openai

# The LangChain demo is part of the starter kit written by `scrutineer init`
pip install "scrutineer-agents[langchain]"
python scrutineer-examples/langchain_quickstart.py
```

## WebUI Dashboard

Scrutineer includes a browser-based dashboard for running scenarios, viewing
traces, and comparing baselines — all wrapping the core Python API.

```bash
# Install with web dependencies
pip install "scrutineer-agents[web]"

# Start the dashboard
scrutineer serve

# Or with a custom port
scrutineer serve --port 9090
```

Then open [http://localhost:8080](http://localhost:8080) in your browser.

Features:
- **Dashboard** — pass/fail stats, recent runs, quick actions
- **Scenarios** — browse, inspect, and run test scenarios
- **Runs** — live execution with step-by-step trace visualization
- **Baselines** — saved results with regression diff comparison
- **Live Console** — real-time log streaming via SSE during test runs

See [src/scrutineer/web/README.md](src/scrutineer/web/README.md) for the full
WebUI guide.

## Architecture

```
src/scrutineer/
├── env.py          # MockTool, MockAPI, MockDatabase, EnvironmentBuilder
├── chaos.py        # ToolFailureInjector, ContextDegradation, CascadingFailures
├── assertions.py   # 20+ behavioral assertions
├── runner.py       # @scrutineer_test decorator, ScenarioRunner
├── reporting.py    # Regression reports, JUnit XML, HTML
├── baseline.py     # JSON baseline storage with git integration
├── otel.py         # OpenTelemetry span model
├── cli.py          # Full CLI: run, list, info, baseline, diff, report
├── adapters/       # LangChain, CrewAI, OpenAI SDK, Generic
└── web/            # FastAPI WebUI dashboard (optional)
    ├── app.py          # FastAPI application factory
    ├── server.py       # Uvicorn entry point
    ├── api/            # REST API routers (scenarios, runs, baselines)
    ├── services/       # Service layer wrapping core modules
    ├── schemas/        # Pydantic request/response models
    └── static/         # Frontend (HTML, CSS, JS)
```

## The Chaos Module (Differentiator)

Scrutineer's chaos injection is what sets it apart:

- **ContextDegradation** — Quadratic acceleration curve matching real context
  window pressure (last 20% is much worse than first 20%)
- **CascadingFailures** — Multi-agent error propagation with dependency graphs
  (database → api_server → ui)
- **SpecDrift** — Agent improvisation under pressure with intensity levels
  and cumulative drift scoring

No other tool tests these production failure modes.

## CLI Commands

```bash
scrutineer init                    # Write the starter scenarios into ./scrutineer-examples
scrutineer run <scenario>          # Run a test scenario
scrutineer list                    # List available scenarios
scrutineer info <scenario>         # Show scenario details
scrutineer baseline record         # Record current state as baseline
scrutineer baseline show           # Show recorded baseline
scrutineer diff                    # Compare current vs baseline
scrutineer report                  # Generate regression report
scrutineer trace <run-id>          # Show execution trace
scrutineer serve                   # Start WebUI dashboard
scrutineer serve --port 9090       # Custom port
```

## Framework Adapters

Scrutineer ships adapters for specific frameworks, plus a generic hook adapter for anything else:

```python
# LangChain — rebinds your_agent.tools so the agent's own call path hits the mocks
from scrutineer.adapters.langchain import wrap_agent
wrapped = wrap_agent(your_agent, tool_map={...}, trace=trace)

# Agents whose tools are bound internally (a create_react_agent Runnable, say)
# cannot be rebound. wrap_agent raises AgentInterceptionError rather than
# quietly letting the real tools run — build the agent against the mocks instead:
wrapped = wrap_agent(agent=None, tool_map={...}, trace=trace, intercept=False)
agent = create_react_agent(model, wrapped.tools.values())

# CrewAI
from scrutineer.adapters.crewai import wrap_crew_agent
wrapped = wrap_crew_agent(your_crew, tool_map={...}, trace=trace)

# OpenAI SDK
from scrutineer.adapters.openai import wrap_openai_agent
wrapped = wrap_openai_agent(your_agent, tool_map={...}, trace=trace)

# Generic (any framework)
from scrutineer.adapters.generic import HookAdapter
adapter = HookAdapter(mock=your_mock, before=hook_fn)
```

## Chaos Example

```python
from scrutineer.chaos import (
    ToolFailureInjector,
    ContextDegradation,
    CascadingFailures,
    ChaosBudget,
)

# Fail 30% of tool calls with timeout errors
injector = ToolFailureInjector(
    failure_type="timeout",
    probability=0.3,
)

# Degrade context with quadratic acceleration
degradation = ContextDegradation(strategy="TRUNCATION")

# Cascade failures from database to API to UI using a custom dependency graph
cascade = CascadingFailures(
    cascade_probability=0.7,
    max_cascade_depth=3,
    dependency_graph={
        "database": "api_server",
        "api_server": "user_interface",
    },
)

# Cap total failures per run
budget = ChaosBudget(max_failures=10)
```

## Documentation

- [Quickstart](docs/QUICKSTART.md) — 5-minute guide from install to first test
- [Chaos Guide](docs/CHAOS_GUIDE.md) — Deep dive on failure injection patterns
- [Adapters Guide](docs/ADAPTERS_GUIDE.md) — How to write custom adapters
- [Integration Testing](docs/INTEGRATION_TESTING.md) — Proof of value with real LangChain tools
- [API Reference](docs/api.md) — Module documentation
- [WebUI Design](docs/WEBUI_DESIGN.md) — Architecture and implementation plan
- [WebUI Guide](src/scrutineer/web/README.md) — Getting started with the dashboard

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=scrutineer --cov-report=html

# Run integration tests only
pytest tests/scrutineer/test_integration_langchain.py -v

# Lint
ruff check src/ tests/
```

## License

MIT
