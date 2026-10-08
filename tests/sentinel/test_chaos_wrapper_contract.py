"""Chaos injectors must work through the wrapper they hand out, from a file.

Two distinct guarantees, both of which were false before this module existed:

1. **Family completeness.** ``ToolFailureInjector``, ``NetworkPartition``,
   ``ClockSkew`` and ``MemoryPressure`` all expose ``wrap()`` and return a
   ``ChaosToolWrapper``. The wrapper's very first line reads
   ``self._injector.tool_name`` and it later reads ``self._injector.failure_type``
   — attributes only ``ToolFailureInjector`` defined, so the other three raised
   ``AttributeError`` the instant they fired. Claiming a family is supported
   while two thirds of it crashes on use is the failure this test prevents.

2. **File reachability.** §4.10: the chaos module is the differentiator and a
   *scenario file* could not reach it. ``compile_chaos`` refused every injector
   but ``tool_failure``, so a customer writing a partition scenario got a loud
   error — better than silence, but the differentiator was unbuyable.
"""

from __future__ import annotations

import pytest

from sentinel import chaos
from sentinel.env import MockTool

yaml = pytest.importorskip("yaml", reason="scenario files are YAML; install .[governance]")


def _wrapping_injectors() -> dict[str, object]:
    """One instance of every injector that hands out a ChaosToolWrapper."""
    return {
        "tool_failure": chaos.ToolFailureInjector(
            tool_name="search", failure_type="timeout", probability=1.0, seed=1
        ),
        "network_partition": chaos.NetworkPartition(
            connectivity={"agent": ["search"]}, partition_probability=1.0, seed=1
        ),
        "clock_skew": chaos.ClockSkew(skew_seconds=5.0, drift_rate=0.1, seed=1),
        "memory_pressure": chaos.MemoryPressure(oom_probability=1.0, seed=1),
    }


@pytest.mark.parametrize("name", sorted(_wrapping_injectors()))
def test_injector_works_through_its_own_wrapper(name):
    """No injector may break inside the wrapper it returns."""
    injector = _wrapping_injectors()[name]
    wrapped = injector.wrap(MockTool("search", response="ok"))

    try:
        result = wrapped(query="x")
        assert result == "ok", "the wrapper returned something other than the tool's response"
    except AttributeError as exc:  # noqa: BLE001 - this is the failure being pinned
        pytest.fail(
            f"{name} cannot be applied through ChaosToolWrapper: {exc}. The wrapper "
            "reads injector.tool_name and injector.failure_type, so every wrapping "
            "injector must define both."
        )
    except Exception:
        pass  # an injected failure is the expected path for a probability=1.0 setup

    assert injector.injection_count >= 1, (
        f"{name} reported no injection at all for an always-on configuration, so a "
        "chaos scenario using it would pass while injecting nothing"
    )


def _write(tmp_path, scenario: dict, name: str = "scenario.yaml"):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(scenario), encoding="utf-8")
    return path


_PARTITION_SCENARIO = {
    "id": "partition-demo",
    "name": "Search behind a network partition",
    "task": "Look up the refund policy",
    "env_config": {
        "tools": {
            "search": {"response": {"results": ["policy"]}},
            "cache": {"response": {"policy": "30-day window"}},
        }
    },
    "chaos": {
        "budget": {"max_failures": 5},
        "injectors": [
            {
                "type": "network_partition",
                "tool": "search",
                "connectivity": {"agent": ["search"]},
                "partition_probability": 1.0,
                "seed": 7,
            }
        ],
    },
    "agent": {
        "type": "script",
        "on_error": "fallback",
        "steps": [{"tool": "search", "args": {"query": "refund policy"}}],
        "fallback": {"tool": "cache", "args": {"key": "policy"}},
    },
    "assertions": [
        {"type": "tool_called", "tool": "search"},
        {"type": "tool_called", "tool": "cache"},
        {"type": "no_silent_failure"},
    ],
}


def test_partition_scenario_is_reachable_from_a_file_and_passes_when_handled(tmp_path):
    """§4.10: a wrapper-based injector must load, inject, and be satisfiable."""
    from sentinel.cli import _load_scenario_file
    from sentinel.runner import ScenarioRunner

    scenario = _load_scenario_file(str(_write(tmp_path, _PARTITION_SCENARIO)))[0]
    result = ScenarioRunner().run(scenario)

    assert result.passed, [a.error_message for a in result.failed_assertions()]
    assert result.trace.tool_calls, "the run produced no tool calls at all"


def test_partition_scenario_is_falsifiable(tmp_path):
    """Same file, one line changed: no fallback => the run must FAIL.

    Without this the PASS above proves nothing — a scenario that cannot fail
    is not a test.
    """
    import copy

    from sentinel.cli import _load_scenario_file
    from sentinel.runner import ScenarioRunner

    unhandled = copy.deepcopy(_PARTITION_SCENARIO)
    unhandled["agent"]["on_error"] = "fail"
    unhandled["agent"].pop("fallback")
    unhandled["assertions"] = [{"type": "tool_called", "tool": "search"}]

    scenario = _load_scenario_file(str(_write(tmp_path, unhandled, "unhandled.yaml")))[0]
    result = ScenarioRunner().run(scenario)

    assert not result.passed, "a partition with no fallback passed — the chaos is not real"
