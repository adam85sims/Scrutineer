"""Tests for the serialisable scenario schema and the file-based run path.

Two things are being pinned here:

1. ``scrutineer.scenario_schema`` compiles declarative assertion/chaos specs, and
   **fails loudly** on anything it cannot honour. A silently ignored key is a test
   that verifies less than its author believes.
2. ``ScenarioRunner`` refuses to report a pass on a scenario that verifies nothing,
   and actually applies chaos declared in a scenario file.
"""

from __future__ import annotations

import pytest

from scrutineer.env import EnvironmentBuilder
from scrutineer.models import AgentTrace
from scrutineer.runner import ScenarioRunner, ScrutineerScenario
from scrutineer.scenario_schema import (
    ScenarioSchemaError,
    assertion_types,
    chaos_injector_types,
    compile_assertions,
    compile_chaos,
)


@pytest.fixture
def budget():
    """A compiled ChaosBudget that fails 'search' every time."""
    return compile_chaos(
        {
            "budget": {"max_failures": 10},
            "injectors": [
                {
                    "type": "tool_failure",
                    "tool": "search",
                    "failure_type": "timeout",
                    "probability": 1.0,
                    "seed": 42,
                }
            ],
        }
    )


@pytest.fixture
def search_env():
    """Environment with a 'search' tool (fails under chaos) and a working 'cache'."""
    return (
        EnvironmentBuilder()
        .mock_tool("search", response={"results": ["live"]})
        .mock_tool("cache", response={"results": ["cached"]})
        .build()
    )


# ──────────────────────────────────────────────────────
# Compiler — registries
# ──────────────────────────────────────────────────────


class TestRegistries:
    def test_assertion_types_excludes_the_prefix(self):
        types = assertion_types()
        assert "tool_called" in types
        assert "graceful_degradation" in types
        assert all(not t.startswith("assert_") for t in types)

    def test_assertion_types_are_sorted_and_unique(self):
        types = assertion_types()
        assert types == sorted(set(types))

    def test_chaos_injector_types(self):
        types = chaos_injector_types()
        assert "tool_failure" in types
        assert types == sorted(set(types))


# ──────────────────────────────────────────────────────
# Compiler — assertions (happy path)
# ──────────────────────────────────────────────────────


class TestCompileAssertions:
    def test_tool_alias_maps_to_tool_name(self):
        (check,) = compile_assertions([{"type": "tool_called", "tool": "search"}])
        assert "tool_name='search'" in check.__name__

    def test_bare_string_spec_for_zero_param_assertion(self):
        (check,) = compile_assertions(["no_tool_errors"])
        assert check.__name__ == "no_tool_errors"

    def test_kwargs_nest_extra_expected_kwargs(self):
        (check,) = compile_assertions(
            [{"type": "tool_called", "tool": "search", "kwargs": {"query": "rates"}}]
        )
        assert "query='rates'" in check.__name__

    def test_order_is_preserved(self):
        checks = compile_assertions(
            ["no_tool_errors", {"type": "tool_called", "tool": "a"}, "step_count"]
        )
        assert [c.__name__.split("(")[0] for c in checks] == [
            "no_tool_errors",
            "tool_called",
            "step_count",
        ]

    def test_empty_and_none_compile_to_empty_list(self):
        assert compile_assertions([]) == []
        assert compile_assertions(None) == []

    def test_compiled_assertion_runs_and_can_pass(self):
        (check,) = compile_assertions([{"type": "tool_called", "tool": "search"}])
        trace = AgentTrace()
        env = EnvironmentBuilder().mock_tool("search", response="ok").build()
        env.set_trace(trace)
        env.get_tool("search")(query="x")
        check(trace)  # must not raise


# ──────────────────────────────────────────────────────
# Compiler — assertions (must fail loudly)
# ──────────────────────────────────────────────────────


class TestCompileAssertionsRejects:
    def test_unknown_type(self):
        with pytest.raises(ScenarioSchemaError, match="Unknown assertion type"):
            compile_assertions([{"type": "nope"}])

    def test_missing_type_key(self):
        with pytest.raises(ScenarioSchemaError, match="missing a 'type' key"):
            compile_assertions([{"tool": "search"}])

    def test_misspelled_parameter_is_not_silently_dropped(self):
        with pytest.raises(ScenarioSchemaError, match="unknown parameter 'toooll'"):
            compile_assertions([{"type": "tool_called", "tool": "x", "toooll": "y"}])

    def test_missing_required_parameter(self):
        with pytest.raises(ScenarioSchemaError, match="missing required parameter"):
            compile_assertions([{"type": "tool_call_count", "tool": "x"}])

    def test_multi_trace_assertion_is_rejected(self):
        with pytest.raises(ScenarioSchemaError, match="multiple traces"):
            compile_assertions([{"type": "state_no_collisions", "key": "k"}])

    def test_kwargs_must_be_a_mapping(self):
        with pytest.raises(ScenarioSchemaError, match="'kwargs' must be a mapping"):
            compile_assertions([{"type": "tool_called", "tool": "x", "kwargs": "no"}])

    def test_kwargs_rejected_when_assertion_takes_none(self):
        with pytest.raises(ScenarioSchemaError, match="not accepted by this assertion"):
            compile_assertions([{"type": "no_tool_errors", "kwargs": {"a": 1}}])

    def test_named_parameter_inside_kwargs_is_rejected(self):
        with pytest.raises(ScenarioSchemaError, match="is a named parameter"):
            compile_assertions(
                [{"type": "tool_called", "tool": "x", "kwargs": {"tool_name": "y"}}]
            )

    def test_auto_budget_without_chaos_block(self):
        with pytest.raises(ScenarioSchemaError, match="declares no chaos block"):
            compile_assertions([{"type": "chaos_resilience", "chaos_budget": "auto"}])

    def test_assertions_must_be_a_list(self):
        with pytest.raises(ScenarioSchemaError, match="must be a list"):
            compile_assertions({"type": "no_tool_errors"})


# ──────────────────────────────────────────────────────
# Compiler — chaos
# ──────────────────────────────────────────────────────


class TestCompileChaos:
    def test_compiles_budget_and_injectors(self, budget):
        assert budget is not None
        assert len(budget.get_injectors()) == 1

    def test_none_and_empty_return_none(self):
        assert compile_chaos(None) is None
        assert compile_chaos({}) is None

    def test_budget_only_is_allowed(self):
        compiled = compile_chaos({"budget": {"max_failures": 2}})
        assert compiled.get_injectors() == []

    def test_unknown_injector_type(self):
        with pytest.raises(ScenarioSchemaError, match="Unknown chaos injector type"):
            compile_chaos({"injectors": [{"type": "nope"}]})

    def test_unsupported_injector_is_rejected_not_dropped(self):
        # Would otherwise be accepted and silently inject nothing.
        with pytest.raises(ScenarioSchemaError, match="not yet applied"):
            compile_chaos({"injectors": [{"type": "context_degradation"}]})

    def test_unknown_chaos_key(self):
        with pytest.raises(ScenarioSchemaError, match="unknown key"):
            compile_chaos({"bogus": 1})

    def test_typo_in_budget_key(self):
        with pytest.raises(ScenarioSchemaError, match="unknown parameter"):
            compile_chaos({"budget": {"max_failur": 5}})

    def test_injector_needs_a_type(self):
        with pytest.raises(ScenarioSchemaError, match="must be a mapping with a 'type'"):
            compile_chaos({"injectors": [{"tool": "search"}]})

    def test_missing_required_injector_parameter(self):
        with pytest.raises(ScenarioSchemaError, match="missing required parameter"):
            compile_chaos({"injectors": [{"type": "tool_failure", "probability": 0.5}]})


# ──────────────────────────────────────────────────────
# Runner — no assertions means no pass
# ──────────────────────────────────────────────────────


class TestNoAssertionsIsNotAPass:
    def test_scenario_with_no_assertions_fails(self):
        """The core false-green fix: nothing verified must not report success."""
        result = ScenarioRunner().run(
            ScrutineerScenario(id="x", name="Verifies nothing", task="t")
        )
        assert result.passed is False
        assert result.error is not None
        assert "no assertions" in result.error.lower()

    def test_the_failure_is_visible_as_an_assertion_result(self):
        result = ScenarioRunner().run(ScrutineerScenario(id="x", name="N", task="t"))
        names = [a.assertion_name for a in result.failed_assertions()]
        assert names == ["no_assertions_declared"]

    def test_summary_does_not_claim_a_pass(self):
        result = ScenarioRunner().run(ScrutineerScenario(id="x", name="N", task="t"))
        assert "[PASS]" not in result.summary
        assert "[FAIL]" in result.summary

    def test_allow_no_assertions_opts_in_deliberately(self):
        """A trace-collection run is still possible, but must be asked for."""
        def agent(task, env, trace):
            from scrutineer.models import Step, StepAction

            trace.add_step(Step(step_id=1, action=StepAction.RESPOND, output="ok"))

        result = ScenarioRunner().run(
            ScrutineerScenario(
                id="probe", name="Probe run", task="t", allow_no_assertions=True
            ),
            agent_fn=agent,
        )
        assert result.passed is True
        assert len(result.trace.steps) == 1

    def test_only_python_callables_still_counts_as_assertions(self):
        def always_ok(trace):
            return None

        result = ScenarioRunner().run(
            ScrutineerScenario(id="x", name="N", task="t", assertions=[always_ok])
        )
        assert result.passed is True
        assert len(result.assertion_results) == 1

    def test_declarative_assertion_that_should_fail_does_fail(self):
        """Proves declarative checks are actually executed, not ignored."""
        result = ScenarioRunner().run(
            ScrutineerScenario(
                id="x",
                name="N",
                task="t",
                assertion_specs=[{"type": "tool_called", "tool": "never_called"}],
            ),
            env=EnvironmentBuilder().mock_tool("search", response="ok").build(),
        )
        assert result.passed is False
        assert "never_called" in result.assertion_results[0].error_message


# ──────────────────────────────────────────────────────
# Runner — declarative chaos is applied
# ──────────────────────────────────────────────────────


class TestDeclarativeChaos:
    def test_chaos_injector_fires_for_a_naive_agent(self, search_env):
        """The injected failure must actually reach the tool call."""
        result = ScenarioRunner().run(
            ScrutineerScenario(
                id="chaos",
                name="Naive agent under chaos",
                task="search",
                chaos_config={
                    "injectors": [
                        {
                            "type": "tool_failure",
                            "tool": "search",
                            "failure_type": "timeout",
                            "probability": 1.0,
                            "seed": 42,
                        }
                    ]
                },
                assertion_specs=[{"type": "tool_called", "tool": "cache"}],
            ),
            agent_fn=_naive_agent,
            env=search_env,
        )
        # Chaos surfaced in the trace...
        failed_calls = [tc for tc in result.trace.tool_calls if tc.error]
        assert [tc.tool_name for tc in failed_calls] == ["search"]
        # ...and the agent, which never fell back, fails the assertion.
        assert result.passed is False
        assert [a.assertion_name for a in result.failed_assertions()] == [
            "tool_called(tool_name='cache')"
        ]

    def test_resilient_agent_passes_under_the_same_chaos(self, search_env):
        """Same chaos, same assertions, an agent that degrades gracefully: PASS."""
        result = ScenarioRunner().run(
            ScrutineerScenario(
                id="chaos",
                name="Resilient agent under chaos",
                task="search",
                chaos_config={
                    "injectors": [
                        {
                            "type": "tool_failure",
                            "tool": "search",
                            "failure_type": "timeout",
                            "probability": 1.0,
                            "seed": 42,
                        }
                    ]
                },
                assertion_specs=[
                    {"type": "tool_called", "tool": "cache"},
                    {"type": "graceful_degradation"},
                ],
            ),
            agent_fn=_resilient_agent,
            env=search_env,
        )
        assert result.passed is True, [a.error_message for a in result.failed_assertions()]
        assert [tc.tool_name for tc in result.trace.tool_calls] == ["search", "cache"]

    def test_chaos_targeting_a_missing_tool_is_an_error(self):
        """Silently skipping an unmatched injector would fake resilience."""
        with pytest.raises(ValueError, match="not in the environment"):
            ScenarioRunner().run(
                ScrutineerScenario(
                    id="chaos",
                    name="Bad target",
                    task="t",
                    chaos_config={
                        "injectors": [
                            {"type": "tool_failure", "tool": "ghost", "probability": 1.0}
                        ]
                    },
                    assertion_specs=["no_tool_errors"],
                ),
                env=EnvironmentBuilder().mock_tool("search", response="ok").build(),
            )

    def test_env_tool_side_effect_key_is_rejected_with_guidance(self):
        with pytest.raises(ValueError, match="chaos"):
            ScenarioRunner().run(
                ScrutineerScenario(
                    id="x",
                    name="N",
                    task="t",
                    env_config={"tools": {"search": {"side_effect": "timeout"}}},
                    assertion_specs=["no_tool_errors"],
                )
            )

    def test_env_error_probability_is_honoured(self):
        """error_probability is serialisable and must actually be forwarded."""
        result = ScenarioRunner().run(
            ScrutineerScenario(
                id="x",
                name="N",
                task="t",
                env_config={
                    "tools": {"search": {"response": "ok", "error_probability": 1.0}}
                },
                assertion_specs=["no_tool_errors"],
            ),
            agent_fn=_calling_agent,
        )
        assert result.passed is False
        assert result.trace.tool_calls[0].error is not None


# ──────────────────────────────────────────────────────
# Stand-in agents (deterministic — the chaos variable is what's under test)
# ──────────────────────────────────────────────────────


def _calling_agent(task, env, trace):
    """Calls 'search' once, swallowing the error so the trace is still produced."""
    try:
        env.get_tool("search")(query=task)
    except Exception:  # noqa: BLE001 - error path is the subject under test
        pass


def _naive_agent(task, env, trace):
    """No fallback strategy: calls the tool, does nothing when it fails."""
    try:
        env.get_tool("search")(query=task)
    except Exception:  # noqa: BLE001 - deliberately unhandled failure
        pass


def _resilient_agent(task, env, trace):
    """Falls back to the cache when the primary tool fails."""
    from scrutineer.models import Step, StepAction

    try:
        env.get_tool("search")(query=task)
    except Exception:  # noqa: BLE001 - the point is to degrade gracefully
        pass
    cached = env.get_tool("cache")(key="rates")
    # The environment is trace-wired, so the tool calls above are already recorded.
    # Re-declaring them in the step's tool_calls would double-count them.
    trace.add_step(
        Step(
            step_id=1,
            action=StepAction.TOOL_CALL,
            input=task,
            output=cached,
        )
    )
