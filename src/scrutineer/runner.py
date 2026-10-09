"""Scrutineer test runner — pytest-native test execution with declarative scenarios.

Provides the ``@scrutineer_test`` decorator for defining behavioral tests
in a declarative way, and the ``ScenarioRunner`` for loading/executing
scenarios programmatically or via CLI.

Usage with pytest decorator:
    import pytest
    from scrutineer.runner import scrutineer_test
    from scrutineer.env import EnvironmentBuilder, MockTool
    from scrutineer.assertions import assert_tool_called

    @scrutineer_test(
        env=(EnvironmentBuilder()
            .mock_tool("search", response={"results": []})
            .build()),
        task="Search for refund policy",
    )
    def test_search_agent(trace, env):
        # trace is pre-created AgentTrace, env is the built Environment
        # Run your agent here, then assert
        assert_tool_called(trace, "search")

Usage with ScenarioRunner:
    from scrutineer.runner import ScenarioRunner, ScrutineerScenario

    scenario = ScrutineerScenario(
        id="refund-001",
        name="Refund agent handles timeout",
        task="Process refund for order #123",
        env_config={"tools": {"search": {"response": "no results"}}},
    )
    runner = ScenarioRunner()
    result = runner.run(scenario, agent_fn=my_agent)
"""

from __future__ import annotations

import functools
import time
import traceback
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any

from scrutineer.env import Environment, EnvironmentBuilder
from scrutineer.models import AgentTrace, Error, ErrorSeverity

# ──────────────────────────────────────────────────────
# AgentConfig — how to instantiate an agent
# ──────────────────────────────────────────────────────


__all__ = [
    "AgentConfig",
    "ScrutineerScenario",
    "TestScenario",
    "ScrutineerAssertionResult",
    "ScrutineerResult",
    "ScenarioRunner",
    "scrutineer_test",
]


@dataclass
class AgentConfig:
    """Configuration for instantiating an agent under test.

    Describes HOW to create the agent, not the agent itself.
    The runner uses this to construct the agent before each test.

    Attributes:
        agent_type: Import path or class name for the agent.
                    e.g. "my_agent:RefundAgent" or a callable factory.
        model: Model identifier (for display/logging; not used to instantiate).
        tools: List of tool names this agent is expected to use.
        prompt: System prompt or prompt template (for display/logging).
        kwargs: Extra keyword arguments passed to the agent constructor.
        factory: A callable that returns the agent instance.
                 If provided, takes precedence over agent_type.
    """

    agent_type: str | None = None
    model: str = "unknown"
    tools: list[str] = field(default_factory=list)
    prompt: str = ""
    kwargs: dict[str, Any] = field(default_factory=dict)
    factory: Callable[..., Any] | None = field(default=None, repr=False)


# ──────────────────────────────────────────────────────
# ScrutineerScenario — declarative test definition
# Named "Scrutineer" prefix to avoid pytest collection.
# ──────────────────────────────────────────────────────


@dataclass
class ScrutineerScenario:
    """A declarative test scenario for scrutineer.

    Encapsulates everything needed to run a behavioral test:
    the agent config, environment setup, chaos injection rules,
    task description, and assertions.

    Scenarios can be defined in code (via @scrutineer_test) or loaded
    from YAML/JSON files (via ScenarioRunner).
    """

    id: str
    name: str
    description: str = ""
    agent_config: AgentConfig | None = None
    environment: Environment | None = None
    env_config: dict[str, Any] = field(default_factory=dict)
    chaos_config: dict[str, Any] = field(default_factory=dict)
    task: str = ""
    assertions: list[Callable[..., None]] = field(default_factory=list)
    timeout_seconds: int = 30
    tags: list[str] = field(default_factory=list)
    #: Declarative assertions loaded from a scenario file (see scrutineer.scenario_schema).
    #: Compiled alongside ``assertions`` at run time so that every loader — CLI, WebUI,
    #: YAML, JSON — behaves identically.
    assertion_specs: list[Any] = field(default_factory=list)
    #: A scenario that declares no assertions verifies nothing, so a run of it fails
    #: rather than reporting a green it did not earn. Set True only to collect a trace
    #: on purpose.
    allow_no_assertions: bool = False
    #: Declarative agent (see scrutineer.scenario_schema.compile_agent). Only used when
    #: no explicit agent_fn is supplied to run().
    agent_spec: dict[str, Any] = field(default_factory=dict)


# TestScenario is the canonical public name (architecture §6.1).
# ScrutineerScenario is kept for backward compatibility.
TestScenario = ScrutineerScenario


# ──────────────────────────────────────────────────────
# ScrutineerResult — outcome of a scenario run
# Named "Scrutineer" prefix to avoid pytest collection.
# ──────────────────────────────────────────────────────


@dataclass
class ScrutineerAssertionResult:
    """Result of a single assertion check."""

    assertion_name: str
    passed: bool
    error_message: str | None = None
    duration_ms: float = 0.0


@dataclass
class ScrutineerResult:
    """Outcome of running a single test scenario.

    Captures pass/fail, the full trace, assertion results, and timing.
    """

    scenario_id: str
    scenario_name: str
    passed: bool
    trace: AgentTrace = field(default_factory=AgentTrace)
    assertion_results: list[ScrutineerAssertionResult] = field(default_factory=list)
    duration_ms: float = 0.0
    error: str | None = None
    timestamp: float = field(default_factory=time.time)

    @property
    def summary(self) -> str:
        """One-line human-readable summary."""
        status = "PASS" if self.passed else "FAIL"
        n_assertions = len(self.assertion_results)
        n_passed = sum(1 for a in self.assertion_results if a.passed)
        return (
            f"[{status}] {self.scenario_name} "
            f"({n_passed}/{n_assertions} assertions, "
            f"{self.duration_ms:.0f}ms)"
        )

    def failed_assertions(self) -> list[ScrutineerAssertionResult]:
        """Get all failed assertions."""
        return [a for a in self.assertion_results if not a.passed]


# TestResult is the canonical public name (architecture §6.2).
# ScrutineerResult is kept for backward compatibility.
TestResult = ScrutineerResult


# ──────────────────────────────────────────────────────
# ScenarioRunner — execute scenarios
# ──────────────────────────────────────────────────────


class ScenarioRunner:
    """Executes test scenarios against agents.

    The runner:
    1. Builds the environment from config (if not pre-built)
    2. Constructs the agent (if agent_config.factory is provided)
    3. Creates an AgentTrace
    4. Invokes the agent's task
    5. Runs assertions against the trace
    6. Returns a ScrutineerResult

    Usage:
        runner = ScenarioRunner()
        result = runner.run(scenario, agent_fn=my_agent_fn)
        assert result.passed
    """

    def run(
        self,
        scenario: ScrutineerScenario,
        agent_fn: Callable[..., Any] | None = None,
        env: Environment | None = None,
    ) -> ScrutineerResult:
        """Run a single test scenario.

        Args:
            scenario: The test scenario to execute.
            agent_fn: Callable that accepts (task, env, trace) and runs
                      the agent. If None, scenario.agent_config.factory is used.
            env: Pre-built environment. Overrides scenario.environment.

        Returns:
            ScrutineerResult with pass/fail status and assertion details.
        """
        start_time = time.time()
        trace = AgentTrace()

        # Resolve environment
        if env is not None:
            resolved_env = env
        elif scenario.environment is not None:
            resolved_env = scenario.environment
        elif scenario.env_config:
            resolved_env = self._build_env(scenario.env_config)
        else:
            resolved_env = Environment()

        # Compile the scenario's declarative assertions and chaos configuration.
        # Both raise ScenarioSchemaError on anything they cannot honour, so a
        # malformed scenario fails loudly instead of quietly verifying nothing.
        from scrutineer.scenario_schema import compile_assertions, compile_chaos

        budget = compile_chaos(scenario.chaos_config)
        checks = list(scenario.assertions) + compile_assertions(
            scenario.assertion_specs, budget=budget
        )

        # A scenario with no assertions proves nothing, so it must not report a pass.
        if not checks and not scenario.allow_no_assertions:
            duration_ms = (time.time() - start_time) * 1000
            message = (
                "Scenario declares no assertions — nothing would be verified. "
                "Add an 'assertions:' block, or set allow_no_assertions: true to "
                "collect a trace deliberately."
            )
            return ScrutineerResult(
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                passed=False,
                trace=trace,
                assertion_results=[
                    ScrutineerAssertionResult(
                        assertion_name="no_assertions_declared",
                        passed=False,
                        error_message=message,
                    )
                ],
                duration_ms=duration_ms,
                error=message,
            )

        # Apply chaos before the trace is attached, so wrapped tools record into it.
        if budget is not None:
            _apply_chaos(budget, resolved_env)

        # Wire trace to environment so tool calls are auto-recorded
        resolved_env.set_trace(trace)

        # Resolve agent function
        if agent_fn is None and scenario.agent_config:
            agent_fn = scenario.agent_config.factory
        if agent_fn is None and scenario.agent_spec:
            from scrutineer.scenario_schema import compile_agent

            agent_fn = compile_agent(scenario.agent_spec)

        # Run the agent
        try:
            if agent_fn is not None:
                agent_fn(
                    task=scenario.task,
                    env=resolved_env,
                    trace=trace,
                )
            trace.finish()
        except Exception as exc:
            trace.add_error(
                Error(
                    message=f"Agent execution failed: {exc}",
                    severity=ErrorSeverity.CRITICAL,
                    recoverable=False,
                )
            )
            trace.finish()
            duration_ms = (time.time() - start_time) * 1000
            return ScrutineerResult(
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                passed=False,
                trace=trace,
                duration_ms=duration_ms,
                error=f"Agent crashed: {exc}\n{traceback.format_exc()}",
            )

        # Run assertions
        assertion_results: list[ScrutineerAssertionResult] = []
        all_passed = True

        for assertion in checks:
            a_start = time.time()
            try:
                assertion(trace)
                assertion_results.append(
                    ScrutineerAssertionResult(
                        assertion_name=getattr(assertion, "__name__", str(assertion)),
                        passed=True,
                        duration_ms=(time.time() - a_start) * 1000,
                    )
                )
            except (AssertionError, Exception) as exc:
                all_passed = False
                assertion_results.append(
                    ScrutineerAssertionResult(
                        assertion_name=getattr(assertion, "__name__", str(assertion)),
                        passed=False,
                        error_message=str(exc),
                        duration_ms=(time.time() - a_start) * 1000,
                    )
                )

        duration_ms = (time.time() - start_time) * 1000
        return ScrutineerResult(
            scenario_id=scenario.id,
            scenario_name=scenario.name,
            passed=all_passed,
            trace=trace,
            assertion_results=assertion_results,
            duration_ms=duration_ms,
        )

    def run_batch(
        self,
        scenarios: list[ScrutineerScenario],
        agent_fn: Callable[..., Any] | None = None,
        max_workers: int = 1,
    ) -> list[ScrutineerResult]:
        """Run multiple scenarios.

        Returns a list of ScrutineerResults in the same order as the input.
        """
        if max_workers <= 1:
            return [self.run(scenario, agent_fn=agent_fn) for scenario in scenarios]

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(self.run, scenario, agent_fn=agent_fn)
                for scenario in scenarios
            ]
            return [f.result() for f in futures]

    def _build_env(self, config: dict[str, Any]) -> Environment:
        """Build an Environment from a configuration dict.

        Config format:
            {
                "tools": {
                    "tool_name": {"response": ..., "latency_ms": ...},
                    ...
                },
                "rate_limit": {"calls_per_minute": 10}
            }
        """
        builder = EnvironmentBuilder()
        tools_config = config.get("tools", {})

        # Only keys that can be honoured from a file are accepted. Anything else
        # raises: a silently dropped tool option means a scenario that does not do
        # what its author believes it does.
        allowed = {"response", "latency_ms", "error_probability"}
        guidance = {
            "side_effect": "use the scenario's 'chaos:' block instead",
            "error_message": "set 'error_message' on a chaos injector instead",
            "response_fn": "callables are not serialisable — use the Python API",
            "error_factory": "callables are not serialisable — use the Python API",
            "call_handler": "internal — use a chaos injector instead",
        }

        for name, tool_cfg in tools_config.items():
            if not isinstance(tool_cfg, dict):
                raise ValueError(
                    f"env_config.tools.{name} must be a mapping, got "
                    f"{type(tool_cfg).__name__}"
                )
            unknown = sorted(set(tool_cfg) - allowed)
            if unknown:
                details = "; ".join(
                    f"{k!r}: {guidance.get(k, 'not supported')}" for k in unknown
                )
                raise ValueError(
                    f"env_config.tools.{name} has unsupported key(s): {details}. "
                    f"Supported: {', '.join(sorted(allowed))}"
                )
            builder.mock_tool(
                name=name,
                response=tool_cfg.get("response"),
                latency_ms=tool_cfg.get("latency_ms", 0.0),
                error_probability=tool_cfg.get("error_probability", 0.0),
            )

        rate_limit = config.get("rate_limit")
        if rate_limit:
            builder.with_rate_limit(**rate_limit)

        return builder.build()


# ──────────────────────────────────────────────────────
# @scrutineer_test — pytest decorator
# ──────────────────────────────────────────────────────


def scrutineer_test(
    env: Environment | EnvironmentBuilder | None = None,
    chaos: Any = None,
    task: str = "",
    timeout_seconds: int = 30,
    tags: list[str] | None = None,
) -> Callable:
    """Pytest decorator for declarative scrutineer test definition.

    Wraps a test function so it receives a pre-built ``trace`` (AgentTrace)
    and ``env`` (Environment) as arguments. The test function can then run
    its agent and assert behaviors.

    The decorator handles:
    - Creating and injecting the AgentTrace
    - Building the environment if an EnvironmentBuilder is provided
    - Optionally wiring chaos injectors into the environment
    - Timing the test execution

    Args:
        env: Pre-built Environment or EnvironmentBuilder. If None, an empty
             Environment is created.
        chaos: ChaosBudget for failure injection. Applied to the env's tools.
        task: The task description for the agent (for logging).
        timeout_seconds: Maximum allowed test duration (informational).
        tags: Classification tags for the test.

    Example:
        @scrutineer_test(
            env=(EnvironmentBuilder()
                .mock_tool("search", response=SEARCH_RESULTS)
                .build()),
            task="Search for refund policy",
        )
        def test_search_agent(trace, env):
            # Run agent, then assert
            assert_tool_called(trace, "search")
    """

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            # Build environment
            if isinstance(env, EnvironmentBuilder):
                resolved_env = env.build()
            elif isinstance(env, Environment):
                resolved_env = env
            else:
                resolved_env = Environment()

            # Apply chaos injectors if provided
            if chaos is not None:
                _apply_chaos(chaos, resolved_env)

            # Create trace
            trace = AgentTrace()

            # Wire trace to environment so tool calls are auto-recorded
            resolved_env.set_trace(trace)

            # Inject trace and env into kwargs for the test function
            kwargs["trace"] = trace
            kwargs["env"] = resolved_env

            # Run the test
            return fn(*args, **kwargs)

        # Attach metadata for discovery/reporting
        wrapper._scrutineer_test = True  # type: ignore[attr-defined]
        wrapper._scrutineer_task = task  # type: ignore[attr-defined]
        wrapper._scrutineer_tags = tags or []  # type: ignore[attr-defined]
        wrapper._scrutineer_timeout = timeout_seconds  # type: ignore[attr-defined]
        wrapper._scrutineer_chaos = chaos  # type: ignore[attr-defined]

        return wrapper

    return decorator


def _apply_chaos(chaos: Any, env: Environment) -> None:
    """Wire chaos injectors into the environment's tools.

    Two mechanisms, both real and both verified by tests:

    * ``ToolFailureInjector.wrap(tool)`` installs a call handler on the mock tool
      **in place**;
    * ``NetworkPartition`` / ``ClockSkew`` / ``MemoryPressure`` ``wrap(tool)`` return a
      ``ChaosToolWrapper`` that must be **substituted** into the environment — which is
      what this function does with the return value.

    Anything else raises rather than being silently skipped — an injector that quietly
    does nothing would let a resilience scenario pass with no chaos applied at all.
    """
    from scrutineer.chaos import ChaosBudget, ChaosToolWrapper

    if not isinstance(chaos, ChaosBudget):
        raise TypeError(f"chaos must be a ChaosBudget, got {type(chaos).__name__}")

    for injector in chaos.get_injectors():
        if not hasattr(injector, "wrap"):
            raise NotImplementedError(
                f"{type(injector).__name__} cannot be applied by this path yet. It is "
                "step-driven (on_step/on_failure) and needs an agent loop this runner "
                "does not provide. It would otherwise be silently skipped and inject "
                "nothing."
            )

        tool_name = getattr(injector, "tool_name", None)
        if not tool_name:
            raise ValueError(
                f"{type(injector).__name__} does not name a target tool, so the runner "
                "cannot know which tool to wire. Give it one in the scenario "
                "(`tool: <name>`)."
            )

        tool = env.get_tool(tool_name)
        if tool is None:
            available = sorted(env.get_tools())
            raise ValueError(
                f"chaos targets tool {tool_name!r}, which is not in the "
                f"environment. Available tools: {available or '(none)'}"
            )

        wrapped = injector.wrap(tool)
        # A wrapper has to replace the tool in the environment; an in-place injector
        # returns the same tool it was handed and needs no substitution.
        if isinstance(wrapped, ChaosToolWrapper):
            env.tools[tool_name] = wrapped
