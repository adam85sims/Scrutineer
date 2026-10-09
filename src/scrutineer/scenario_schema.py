"""Serialisable scenario schema — compile declarative specs into assertions and chaos injectors.

YAML and JSON scenarios cannot carry Python callables or injector instances, so the
file format declares *specifications* and this module compiles them into the objects
``ScenarioRunner`` needs.

The guiding rule is **fail loudly, never silently ignore**. A scenario that names an
unknown assertion, a misspelled parameter, or a chaos injector the file path cannot
honour must raise rather than quietly do nothing — silently dropped configuration is
precisely how a test suite ends up reporting a green it did not earn.

Specification shapes::

    assertions:
      - type: tool_called
        tool: search
      - type: tool_call_count
        tool: search
        expected_count: 1
      - type: graceful_degradation
      - type: chaos_resilience
        chaos_budget: auto          # the runner substitutes its compiled budget

    chaos:
      budget:
        max_failures: 10
      injectors:
        - type: tool_failure
          tool: search
          failure_type: timeout
          probability: 1.0
          error_message: "Search API timed out after 30s"
"""

from __future__ import annotations

import functools
import inspect
from collections.abc import Callable
from typing import Any, cast

from scrutineer import assertions as _assertions
from scrutineer import chaos as _chaos
from scrutineer.script_agent import ON_ERROR_POLICIES, ScriptedAgent

__all__ = [
    "ScenarioSchemaError",
    "assertion_types",
    "chaos_injector_types",
    "compile_agent",
    "compile_assertion",
    "compile_assertions",
    "compile_chaos",
    "describe",
]


class ScenarioSchemaError(ValueError):
    """A scenario specification is invalid or names something unsupported."""


# ── Type registries ──────────────────────────────────────

#: Assertion names accepted in scenario files, mapped to the callable that implements
#: them. ``type: tool_called`` resolves to ``assert_tool_called``.
_ASSERTION_PREFIX = "assert_"

#: Assertions that need more than one trace. A single-scenario file run produces
#: exactly one trace, so these cannot be expressed here — they are rejected rather
#: than wrapped, because wrapping would make them silently vacuous.
_MULTI_TRACE_ASSERTIONS = frozenset(
    {"state_consistent_across_traces", "state_no_collisions"}
)

#: Chaos injectors a scenario file may declare, mapped to their class.
_CHAOS_TYPES: dict[str, type] = {
    "tool_failure": _chaos.ToolFailureInjector,
    "context_degradation": _chaos.ContextDegradation,
    "cascading_failures": _chaos.CascadingFailures,
    "spec_drift": _chaos.SpecDrift,
    "network_partition": _chaos.NetworkPartition,
    "clock_skew": _chaos.ClockSkew,
    "memory_pressure": _chaos.MemoryPressure,
}

#: Injectors the file-based runner can genuinely apply today.
#:
#: Two mechanisms qualify, because ``_apply_chaos`` implements both:
#:
#: * ``tool_failure`` — ``wrap()`` installs a call handler on the tool in place;
#: * ``network_partition`` / ``clock_skew`` / ``memory_pressure`` — ``wrap()`` returns a
#:   ``ChaosToolWrapper``, which the runner substitutes into the environment.
#:
#: Both need the scenario to name a target tool (``tool: <name>``), since the runner has
#: to know which tool to wire.
#:
#: Still rejected, loudly: ``context_degradation``, ``spec_drift`` and
#: ``cascading_failures``. These are step-driven (``on_step`` / ``on_failure``) and
#: operate on an agent's *context* — which the scripted reference agent does not have, so
#: wiring them to it would compute a degradation curve and throw it away. They need a real
#: agent (see planning/COMMERCIAL_READINESS_2026-09-13.md §4.4), not a harness change.
_WRAPPABLE_INJECTORS = frozenset(
    {"tool_failure", "network_partition", "clock_skew", "memory_pressure"}
)

#: Friendly YAML key aliases. ``tool: search`` is the natural spelling in a file;
#: the Python API calls the parameter ``tool_name``.
_PARAM_ALIASES = {"tool": "tool_name"}

#: Marker meaning "supply the scenario's compiled ChaosBudget here".
_AUTO = "auto"


def _assertion_callable(name: str) -> Callable[..., None]:
    """Resolve an assertion type name to its implementation, or raise."""
    fn = getattr(_assertions, _ASSERTION_PREFIX + name, None)
    if fn is None or not callable(fn):
        raise ScenarioSchemaError(
            f"Unknown assertion type {name!r}. Valid types: "
            + ", ".join(assertion_types())
        )
    return cast("Callable[..., None]", fn)


def assertion_types() -> list[str]:
    """All assertion type names accepted in a scenario file."""
    return sorted(
        n[len(_ASSERTION_PREFIX) :]
        for n in getattr(_assertions, "__all__", dir(_assertions))
        if n.startswith(_ASSERTION_PREFIX) and callable(getattr(_assertions, n, None))
    )


def chaos_injector_types() -> list[str]:
    """All chaos injector type names accepted in a scenario file."""
    return sorted(_CHAOS_TYPES)


def _build_kwargs(fn: Callable[..., Any], spec: dict[str, Any], *, what: str) -> dict:
    """Validate and translate spec keys into keyword arguments for ``fn``.

    Unknown parameters are an error, not a warning: a misspelled key silently
    dropped is a test that verifies less than its author believes. Parameters a
    function accepts via ``**kwargs`` (``assert_tool_called``'s expected-kwarg
    matching) must be nested under an explicit ``kwargs:`` key, so that a typo at
    the top level is still caught.
    """
    try:
        sig = inspect.signature(fn)
    except (TypeError, ValueError):  # pragma: no cover - builtins only
        return {}

    accepts_extra = any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values()
    )
    valid = {
        n
        for n, p in sig.parameters.items()
        if p.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    # The bound receiver and the trace are never supplied from the file.
    valid.discard("trace")
    valid.discard("self")

    required = {
        n
        for n, p in sig.parameters.items()
        if n not in ("trace", "self")
        and p.default is inspect.Parameter.empty
        and p.kind
        in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }

    kwargs: dict[str, Any] = {}
    for raw_key, value in spec.items():
        if raw_key == "type":
            continue

        if raw_key == "kwargs":
            if not isinstance(value, dict):
                raise ScenarioSchemaError(f"{what}: 'kwargs' must be a mapping")
            if not accepts_extra:
                raise ScenarioSchemaError(
                    f"{what}: 'kwargs' is not accepted by this assertion"
                )
            for k, v in value.items():
                if k in valid:
                    raise ScenarioSchemaError(
                        f"{what}: {k!r} is a named parameter — set it at the top "
                        "level, not inside 'kwargs'"
                    )
                kwargs[k] = v
            continue

        key = _PARAM_ALIASES.get(raw_key, raw_key)
        if key not in valid:
            raise ScenarioSchemaError(
                f"{what}: unknown parameter {raw_key!r}. Valid parameters: "
                + (", ".join(sorted(valid)) or "(none)")
                + ("; extra expected-kwargs go under 'kwargs'" if accepts_extra else "")
            )
        kwargs[key] = value

    missing = required - set(kwargs)
    if missing:
        raise ScenarioSchemaError(
            f"{what}: missing required parameter(s): " + ", ".join(sorted(missing))
        )

    return kwargs


def compile_assertion(
    spec: dict[str, Any] | str,
    *,
    budget: Any = None,
) -> Callable[..., None]:
    """Compile one assertion specification into a ``callable(trace)``.

    Args:
        spec: A dict with a ``type`` key, or a bare type name string for assertions
            that take no parameters (e.g. ``"no_tool_errors"``).
        budget: The scenario's compiled ``ChaosBudget``, substituted wherever a spec
            uses the value ``"auto"`` — this is how ``chaos_resilience`` receives the
            budget the runner actually applied.

    Raises:
        ScenarioSchemaError: unknown type, unknown parameter, or an assertion that
            cannot be expressed against a single trace.
    """
    if isinstance(spec, str):
        spec = {"type": spec}
    if not isinstance(spec, dict):
        raise ScenarioSchemaError(
            f"Each assertion must be a mapping or a type name, got {type(spec).__name__}"
        )

    name = spec.get("type")
    if not name or not isinstance(name, str):
        raise ScenarioSchemaError(f"Assertion is missing a 'type' key: {spec!r}")

    if name in _MULTI_TRACE_ASSERTIONS:
        raise ScenarioSchemaError(
            f"Assertion {name!r} compares multiple traces and cannot be expressed in a "
            "single-scenario file. Use the Python API with run_batch results instead."
        )

    fn = _assertion_callable(name)
    kwargs = _build_kwargs(fn, spec, what=f"assertion {name!r}")

    # Naming is taken before substitution so reports show 'auto' rather than a
    # memory address for the injected budget.
    display = ", ".join(
        f"{k}={'auto' if v == _AUTO else v!r}" for k, v in kwargs.items()
    )

    for key, value in kwargs.items():
        if value == _AUTO:
            if key != "chaos_budget":
                raise ScenarioSchemaError(
                    f"assertion {name!r}: 'auto' is only valid for chaos_budget"
                )
            if budget is None:
                raise ScenarioSchemaError(
                    f"assertion {name!r} uses chaos_budget: auto but the scenario "
                    "declares no chaos block"
                )
            kwargs[key] = budget

    bound = functools.partial(fn, **kwargs)

    def compiled(trace: Any) -> None:
        bound(trace)

    compiled.__name__ = f"{name}({display})" if display else name
    compiled.__doc__ = fn.__doc__
    return compiled


def compile_assertions(
    specs: list[Any] | None,
    *,
    budget: Any = None,
) -> list[Callable[..., None]]:
    """Compile a list of assertion specifications. Order is preserved."""
    if not specs:
        return []
    if not isinstance(specs, list):
        raise ScenarioSchemaError(
            f"'assertions' must be a list, got {type(specs).__name__}"
        )
    return [compile_assertion(spec, budget=budget) for spec in specs]


def compile_chaos(config: dict[str, Any] | None) -> Any:
    """Compile a ``chaos`` block into a ``ChaosBudget``, or return ``None``.

    Raises:
        ScenarioSchemaError: unknown injector type, unknown parameter, or an injector
            that cannot yet be applied by the file-based runner.
    """
    if not config:
        return None
    if not isinstance(config, dict):
        raise ScenarioSchemaError(
            f"'chaos' must be a mapping, got {type(config).__name__}"
        )

    unknown = set(config) - {"budget", "injectors"}
    if unknown:
        raise ScenarioSchemaError(
            f"'chaos' has unknown key(s): {', '.join(sorted(unknown))}. "
            "Valid keys: budget, injectors"
        )

    budget_cfg = config.get("budget") or {}
    if not isinstance(budget_cfg, dict):
        raise ScenarioSchemaError("'chaos.budget' must be a mapping")

    budget_kwargs = _build_kwargs(_chaos.ChaosBudget.__init__, {"type": None, **budget_cfg},
                                  what="chaos.budget")
    budget = _chaos.ChaosBudget(**budget_kwargs)

    injector_specs = config.get("injectors") or []
    if not isinstance(injector_specs, list):
        raise ScenarioSchemaError("'chaos.injectors' must be a list")

    for spec in injector_specs:
        if not isinstance(spec, dict) or not spec.get("type"):
            raise ScenarioSchemaError(
                f"Each chaos injector must be a mapping with a 'type': {spec!r}"
            )
        itype = spec["type"]
        cls = _CHAOS_TYPES.get(itype)
        if cls is None:
            raise ScenarioSchemaError(
                f"Unknown chaos injector type {itype!r}. Valid types: "
                + ", ".join(chaos_injector_types())
            )
        if itype not in _WRAPPABLE_INJECTORS:
            raise ScenarioSchemaError(
                f"Chaos injector {itype!r} is not yet applied by the file-based "
                "runner. Declaring it here would silently inject nothing. "
                "Supported in scenario files: "
                + ", ".join(sorted(_WRAPPABLE_INJECTORS))
                + ". (Step-driven injectors need on_step/on_failure hooks that the "
                "file runner does not implement yet.)"
            )
        kwargs = _build_kwargs(cls.__init__, spec, what=f"chaos injector {itype!r}")
        budget.add(cls(**kwargs))

    return budget


def compile_agent(spec: dict[str, Any] | None) -> Any:
    """Compile an ``agent`` block into a runnable agent function, or return ``None``.

    Only the built-in ``script`` reference agent is supported. It is a deterministic
    stand-in for exercising the harness and the chaos injectors, not a real agent — see
    ``scrutineer.script_agent``.

    Raises:
        ScenarioSchemaError: unknown type, unknown key, or a malformed step/fallback.
    """
    if not spec:
        return None
    if not isinstance(spec, dict):
        raise ScenarioSchemaError(f"'agent' must be a mapping, got {type(spec).__name__}")

    unknown = set(spec) - {"type", "steps", "on_error", "fallback"}
    if unknown:
        raise ScenarioSchemaError(
            f"'agent' has unknown key(s): {', '.join(sorted(unknown))}. "
            "Valid keys: type, steps, on_error, fallback"
        )

    agent_type = spec.get("type", "script")
    if agent_type != "script":
        raise ScenarioSchemaError(
            f"Unknown agent type {agent_type!r}. The file format supports 'script' "
            "(a deterministic reference agent). For a real agent use the Python API: "
            "ScenarioRunner().run(scenario, agent_fn=...)"
        )

    steps = spec.get("steps") or []
    if not isinstance(steps, list):
        raise ScenarioSchemaError("'agent.steps' must be a list")
    for step in steps:
        _validate_step(step, what="agent.steps")

    fallback = spec.get("fallback")
    if fallback is not None:
        _validate_step(fallback, what="agent.fallback")

    on_error = spec.get("on_error", "fail")
    if on_error not in ON_ERROR_POLICIES:
        raise ScenarioSchemaError(
            f"agent.on_error must be one of {', '.join(ON_ERROR_POLICIES)}; "
            f"got {on_error!r}"
        )

    return ScriptedAgent(steps=steps, on_error=on_error, fallback=fallback)


def _validate_step(step: Any, *, what: str) -> None:
    """A step is {'tool': name, 'args': {...}} — nothing else is honoured."""
    if not isinstance(step, dict):
        raise ScenarioSchemaError(f"{what}: each step must be a mapping, got {step!r}")
    if not step.get("tool"):
        raise ScenarioSchemaError(f"{what}: step is missing a 'tool' key: {step!r}")
    unknown = set(step) - {"tool", "args"}
    if unknown:
        raise ScenarioSchemaError(
            f"{what}: unknown key(s) {', '.join(sorted(unknown))} in step "
            f"{step.get('tool')!r}. Valid keys: tool, args"
        )
    if "args" in step and not isinstance(step["args"], dict):
        raise ScenarioSchemaError(f"{what}: 'args' must be a mapping")


def describe(specs: list[Any] | None) -> list[str]:
    """Human-readable names for a list of assertion specs (for reports and docs)."""
    out = []
    for spec in specs or []:
        if isinstance(spec, str):
            out.append(spec)
        elif isinstance(spec, dict):
            params = ", ".join(f"{k}={v!r}" for k, v in spec.items() if k != "type")
            out.append(f"{spec.get('type')}({params})" if params else str(spec.get("type")))
        else:
            out.append(repr(spec))
    return out
