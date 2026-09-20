"""Guard tests for the shipped demo scenarios.

The 8 scenarios under ``examples/demo-scenarios/`` are the ones the WebUI shows
to first-run users and the ones the demo-data generator runs. They previously
declared no assertions and invented ``env_config`` keys no loader supported, so
they reported a green without verifying anything. These tests pin the two
properties that failure was missing:

* every scenario declares assertions, and
* every scenario is **falsifiable** — it passes when the agent handles the
  chaos and fails when it does not.

They read real scenario files and run them through the real runner; no state is
mutated, so they are parallel-safe and order-independent.
"""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from sentinel.cli import _load_scenario_file
from sentinel.runner import ScenarioRunner

pytest.importorskip("yaml", reason="demo scenarios are YAML; install .[governance]")

DEMO_DIR = Path(__file__).resolve().parents[2] / "examples" / "demo-scenarios"
DEMO_FILES = sorted(DEMO_DIR.glob("*.yaml"))


def _unhandled(scenario):
    """The declared scenario with the agent's chaos left unhandled."""
    variant = copy.deepcopy(scenario)
    spec = dict(variant.agent_spec or {})
    spec["on_error"] = "fail"
    spec.pop("fallback", None)
    variant.agent_spec = spec
    return variant


def test_demo_scenarios_exist():
    assert DEMO_FILES, f"no demo scenarios found in {DEMO_DIR}"


@pytest.mark.parametrize("path", DEMO_FILES, ids=lambda p: p.stem)
def test_demo_scenario_declares_assertions_and_chaos(path):
    scenario = _load_scenario_file(str(path))[0]
    assert scenario.assertion_specs, (
        f"{path.name} declares no assertions — it would verify nothing"
    )
    assert scenario.chaos_config, f"{path.name} declares no chaos block"
    assert scenario.agent_spec, f"{path.name} declares no agent (subject under test)"


@pytest.mark.parametrize("path", DEMO_FILES, ids=lambda p: p.stem)
def test_demo_scenario_passes_when_chaos_handled(path):
    scenario = _load_scenario_file(str(path))[0]
    result = ScenarioRunner().run(scenario)
    assert result.passed, (
        f"{path.name} failed even though its agent handles the chaos: "
        f"{[(a.assertion_name, a.error_message) for a in result.assertion_results]}"
    )


@pytest.mark.parametrize("path", DEMO_FILES, ids=lambda p: p.stem)
def test_demo_scenario_fails_when_chaos_unhandled(path):
    scenario = _load_scenario_file(str(path))[0]
    result = ScenarioRunner().run(_unhandled(scenario))
    assert not result.passed, (
        f"{path.name} passed with the chaos unhandled — the scenario cannot "
        "distinguish a resilient agent from a crashing one"
    )
