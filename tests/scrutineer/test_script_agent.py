"""Tests for the deterministic scripted reference agent and its schema compiler.

The scripted agent exists so a scenario *file* can supply a subject. Its error policy
(``on_error``) is the behavioural variable that makes a chaos scenario falsifiable:
identical chaos plus a different policy must produce a different verdict.
"""

from __future__ import annotations

import pytest

from scrutineer.env import EnvironmentBuilder
from scrutineer.models import AgentTrace
from scrutineer.scenario_schema import ScenarioSchemaError, compile_agent
from scrutineer.script_agent import ON_ERROR_POLICIES, ScriptedAgent


@pytest.fixture
def env():
    """Environment where 'boom' and 'ok' and 'cache' all exist."""
    return (
        EnvironmentBuilder()
        .mock_tool("boom", response="should not be reached")
        .mock_tool("ok", response="fine")
        .mock_tool("cache", response="cached")
        .build()
    )


@pytest.fixture
def traced_env(env):
    """Environment with the trace wired, no chaos."""
    trace = AgentTrace()
    env.set_trace(trace)
    return env, trace


@pytest.fixture
def failing_env():
    """Environment whose 'boom' tool always fails, with the trace wired afterwards.

    Order matters: ``Environment.set_trace`` replaces each tool with a ``_TracedTool``,
    so a chaos injector applied *after* it wraps the traced proxy rather than the tool
    and never fires. The runner applies chaos first for exactly this reason.
    """
    from scrutineer.chaos import ToolFailureInjector

    env = (
        EnvironmentBuilder()
        .mock_tool("boom", response="should not be reached")
        .mock_tool("cache", response="cached")
        .build()
    )
    ToolFailureInjector(
        tool_name="boom", failure_type="error", probability=1.0, seed=1
    ).wrap(env.get_tool("boom"))

    trace = AgentTrace()
    env.set_trace(trace)
    return env, trace


# ──────────────────────────────────────────────────────
# compile_agent — schema validation
# ──────────────────────────────────────────────────────


class TestCompileAgent:
    def test_none_and_empty_return_none(self):
        assert compile_agent(None) is None
        assert compile_agent({}) is None

    def test_defaults_to_script_with_fail_policy(self):
        agent = compile_agent({"steps": [{"tool": "ok"}]})
        assert isinstance(agent, ScriptedAgent)
        assert agent.on_error == "fail"

    def test_paths_passed_in_yaml_are_extracted(self):
        agent = compile_agent(
            {
                "steps": [{"tool": "ok", "args": {"a": 1}}],
                "fallback": {"tool": "cache", "args": {"k": "v"}},
                "on_error": "fallback",
            }
        )
        assert agent.steps == [{"tool": "ok", "args": {"a": 1}}]
        assert agent.fallback == {"tool": "cache", "args": {"k": "v"}}

    def test_real_agent_types_are_refused_with_guidance(self):
        with pytest.raises(ScenarioSchemaError, match="Python API"):
            compile_agent({"type": "langchain", "steps": [{"tool": "ok"}]})

    def test_unknown_agent_key(self):
        with pytest.raises(ScenarioSchemaError, match="unknown key"):
            compile_agent({"steps": [{"tool": "ok"}], "prompt": "hi"})

    def test_invalid_on_error(self):
        with pytest.raises(ScenarioSchemaError, match="on_error must be one of"):
            compile_agent({"steps": [{"tool": "ok"}], "on_error": "retry"})

    def test_fallback_policy_requires_a_fallback_block(self):
        with pytest.raises(ValueError, match="requires a 'fallback' block"):
            compile_agent({"steps": [{"tool": "ok"}], "on_error": "fallback"})

    def test_step_missing_tool(self):
        with pytest.raises(ScenarioSchemaError, match="missing a 'tool' key"):
            compile_agent({"steps": [{"args": {}}]})

    def test_step_unknown_key(self):
        with pytest.raises(ScenarioSchemaError, match="unknown key"):
            compile_agent({"steps": [{"tool": "ok", "timeout": 5}]})

    def test_step_args_must_be_a_mapping(self):
        with pytest.raises(ScenarioSchemaError, match="'args' must be a mapping"):
            compile_agent({"steps": [{"tool": "ok", "args": "nope"}]})

    def test_steps_must_be_a_list(self):
        with pytest.raises(ScenarioSchemaError, match="'agent.steps' must be a list"):
            compile_agent({"steps": {"tool": "ok"}})

    def test_every_policy_has_a_compiled_form(self):
        for policy in ON_ERROR_POLICIES:
            spec = {"steps": [{"tool": "ok"}], "on_error": policy}
            if policy == "fallback":
                spec["fallback"] = {"tool": "cache"}
            assert compile_agent(spec).on_error == policy


# ──────────────────────────────────────────────────────
# ScriptedAgent — behaviour of each error policy
# ──────────────────────────────────────────────────────


class TestScriptedAgentBehaviour:
    def test_calls_the_declared_tools_in_order(self, traced_env):
        env, trace = traced_env
        agent = ScriptedAgent(steps=[{"tool": "ok"}, {"tool": "cache"}])
        agent(task="t", env=env, trace=trace)
        assert [tc.tool_name for tc in trace.tool_calls] == ["ok", "cache"]

    def test_args_are_forwarded(self, traced_env):
        env, trace = traced_env
        agent = ScriptedAgent(steps=[{"tool": "ok", "args": {"a": 1}}])
        agent(task="t", env=env, trace=trace)
        assert trace.tool_calls[0].arguments == {"a": 1}

    def test_fail_policy_lets_the_error_propagate(self, failing_env):
        env, trace = failing_env
        agent = ScriptedAgent(steps=[{"tool": "boom"}], on_error="fail")
        with pytest.raises(Exception):  # noqa: B017 - any failure is correct here
            agent(task="t", env=env, trace=trace)

    def test_continue_policy_swallows_and_carries_on(self, failing_env):
        env, trace = failing_env
        agent = ScriptedAgent(
            steps=[{"tool": "boom"}, {"tool": "cache"}], on_error="continue"
        )
        agent(task="t", env=env, trace=trace)
        # The error was recorded and the plan continued to the next step.
        assert trace.errors, "the failure should be recorded in the trace"
        assert "cache" in [tc.tool_name for tc in trace.tool_calls]

    def test_fallback_policy_degrades_to_the_declared_tool(self, failing_env):
        env, trace = failing_env
        agent = ScriptedAgent(
            steps=[{"tool": "boom"}],
            on_error="fallback",
            fallback={"tool": "cache"},
        )
        agent(task="t", env=env, trace=trace)
        assert [tc.tool_name for tc in trace.tool_calls] == ["boom", "cache"]

    def test_chaos_applied_after_set_trace_silently_does_nothing(self, env):
        """Pins the ordering constraint the runner depends on.

        This is the failure mode the whole project is about: no error, no warning,
        the injected fault simply never happens.
        """
        from scrutineer.chaos import ToolFailureInjector

        trace = AgentTrace()
        env.set_trace(trace)  # trace wired FIRST
        ToolFailureInjector(
            tool_name="boom", failure_type="error", probability=1.0, seed=1
        ).wrap(env.get_tool("boom"))

        agent = ScriptedAgent(steps=[{"tool": "boom"}], on_error="fail")
        agent(task="t", env=env, trace=trace)  # must NOT raise
        assert [tc.error for tc in trace.tool_calls] == [None]

    def test_unknown_tool_names_the_available_ones(self, traced_env):
        env, trace = traced_env
        agent = ScriptedAgent(steps=[{"tool": "ghost"}])
        with pytest.raises(ValueError, match="not in the environment"):
            agent(task="t", env=env, trace=trace)

    def test_empty_plan_is_an_error(self, traced_env):
        env, trace = traced_env
        with pytest.raises(ValueError, match="no steps"):
            ScriptedAgent(steps=[])(task="t", env=env, trace=trace)

    def test_repr_is_useful(self):
        assert "ScriptedAgent" in repr(ScriptedAgent(steps=[{"tool": "ok"}]))
