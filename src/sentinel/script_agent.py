"""A deterministic, script-declared reference agent.

IMPORTANT — what this is and is not
-----------------------------------
This is a **reference subject for testing the harness and the chaos injectors**, not a
substitute for a real agent. It follows a declared step plan; it does not reason, and it
makes no decisions beyond the error-handling policy you give it.

That policy is the point. ``on_error`` is a genuine behavioural variable:

* ``fail``      — the error propagates; the agent crashes.
* ``continue``  — the error is swallowed; the plan carries on.
* ``fallback``  — the agent degrades to a declared fallback tool and stops.

So a chaos scenario can hold a tool failure constant and vary *only* the agent's
resilience, and the assertions can tell the two apart. That is a real, falsifiable
comparison — unlike a demo that asserts a hardcoded plan executed the way it was
hardcoded.

For real agents, use the Python API: ``ScenarioRunner().run(scenario, agent_fn=...)``.
"""

from __future__ import annotations

from typing import Any

__all__ = ["ScriptedAgent", "ON_ERROR_POLICIES"]

#: Accepted error-handling policies for a scripted agent.
ON_ERROR_POLICIES = ("fail", "continue", "fallback")


class ScriptedAgent:
    """Runs a declared list of tool calls, with a declared error policy."""

    def __init__(
        self,
        steps: list[dict[str, Any]],
        on_error: str = "fail",
        fallback: dict[str, Any] | None = None,
    ) -> None:
        if on_error not in ON_ERROR_POLICIES:
            raise ValueError(
                f"on_error must be one of {', '.join(ON_ERROR_POLICIES)}; got {on_error!r}"
            )
        if on_error == "fallback" and not fallback:
            raise ValueError("on_error: fallback requires a 'fallback' block")
        self.steps = steps
        self.on_error = on_error
        self.fallback = fallback

    # The runner calls agent_fn(task=..., env=..., trace=...).
    def __call__(self, task: str, env: Any, trace: Any) -> None:
        """Execute the plan. Raises whatever the policy says it should."""
        if not self.steps:
            raise ValueError("scripted agent has no steps to run")

        for index, step in enumerate(self.steps):
            try:
                self._call(env, trace, step, index)
            except Exception as exc:  # noqa: BLE001 - the policy decides what happens
                if self.on_error == "fail":
                    raise
                trace.add_error(_as_trace_error(exc, step))
                # 'continue' falls through to the next step; 'fallback' degrades and
                # stops, since a plan that has lost its primary tool is over.
                if self.on_error == "fallback":
                    assert self.fallback is not None  # guaranteed by __init__
                    self._call(env, trace, self.fallback, len(self.steps))
                    return

    def _call(self, env: Any, trace: Any, step: dict[str, Any], index: int) -> Any:
        """Invoke one declared tool call and record it as a step."""
        from sentinel.models import Step, StepAction

        tool_name = step["tool"]
        tool = env.get_tool(tool_name)
        if tool is None:
            available = sorted(env.get_tools())
            raise ValueError(
                f"scripted agent step targets tool {tool_name!r}, which is not in the "
                f"environment. Available tools: {available or '(none)'}"
            )

        output = tool(**step.get("args", {}))
        # The environment is trace-wired, so the tool call itself is already recorded
        # in trace.tool_calls; this step gives the trace narrative structure.
        trace.add_step(
            Step(
                step_id=index + 1,
                action=StepAction.TOOL_CALL,
                input={"tool": tool_name, "args": step.get("args", {})},
                output=output,
            )
        )
        return output

    def __repr__(self) -> str:
        return (
            f"ScriptedAgent(steps={[s.get('tool') for s in self.steps]}, "
            f"on_error={self.on_error!r})"
        )


def _as_trace_error(exc: Exception, step: dict[str, Any]) -> Any:
    """Convert a tool exception into a trace Error for the degraded paths."""
    from sentinel.models import Error, ErrorSeverity

    return Error(
        message=f"Tool {step.get('tool')!r} failed: {exc}",
        severity=ErrorSeverity.HIGH,
        recoverable=True,
    )
