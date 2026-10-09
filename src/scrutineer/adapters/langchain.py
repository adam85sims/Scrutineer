"""LangChain agent adapter for Scrutineer.

Bridges scrutineer's mock tool layer to LangChain agents for behavioral testing.
Intercepts tool calls, captures them into AgentTrace, and optionally injects
failures via the chaos layer.

Dependencies (all optional):
    - langchain-core >= 0.2: BaseTool, Runnable, tool invocation protocols

Usage:
    from scrutineer.adapters.langchain import ScrutineerToolAdapter, wrap_agent
    from scrutineer.env import MockTool
    from scrutineer.models import AgentTrace

    # Wrap individual tools
    trace = AgentTrace()
    adapter = ScrutineerToolAdapter(
        tool=real_langchain_tool,
        mock=MockTool("search", response=SEARCH_RESULTS),
        trace=trace,
    )

    # Wrap entire agent (all tools at once)
    wrapped = wrap_agent(
        agent=agent,
        tool_map={"search": mock_search, "email": mock_email},
        trace=trace,
    )
"""

from __future__ import annotations

import time
from typing import Any

from scrutineer.env import MockTool
from scrutineer.models import AgentTrace, ToolCall

try:
    from langchain_core.tools import BaseTool
except ImportError:
    BaseTool = None  # type: ignore[misc,assignment]


class AgentInterceptionError(RuntimeError):
    """Raised when Scrutineer cannot replace an agent's tools with mocks.

    Scrutineer must never fall back to letting a wrapped agent call its real
    tools. That is the failure mode where a production API or database write
    happens while the run reports success and the trace stays empty — see
    planning/COMMERCIAL_READINESS_2026-09-13.md §4.3. If the tools cannot be
    rebound, the run stops instead.
    """


def _record_mock_call(mock: MockTool, trace: AgentTrace, kwargs: dict[str, Any]) -> Any:
    """Execute a mock tool and record the call into the trace.

    Shared by the duck-typed adapter and the real LangChain tool, so both
    interception paths produce identical traces.
    """
    start = time.time()
    result = None
    error_msg = None

    try:
        result = mock(**kwargs)
    except Exception as exc:
        error_msg = str(exc)
        raise
    finally:
        duration_ms = (time.time() - start) * 1000
        tool_call = ToolCall(
            tool_name=mock.name,
            arguments=kwargs,
            result=result,
            duration_ms=duration_ms,
            error=error_msg,
        )
        trace.add_tool_call(tool_call)

    return result


if BaseTool is not None:

    class MockBackedTool(BaseTool):
        """A real LangChain tool whose implementation is a scrutineer MockTool.

        This is the object substituted into the agent's tool list, so the
        agent's own call path reaches scrutineer instead of the real
        implementation. ``args_schema`` is deliberately left unset: a mock
        accepts whatever the scenario passes and decides its own response, so
        there is nothing to validate.
        """

        name: str = "mock"
        description: str = ""
        scrutineer_mock: Any = None
        scrutineer_trace: Any = None

        def _run(self, *args: Any, **kwargs: Any) -> Any:
            return self._scrutineer_call(args, kwargs)

        async def _arun(self, *args: Any, **kwargs: Any) -> Any:
            return self._scrutineer_call(args, kwargs)

        def _scrutineer_call(self, args: tuple, kwargs: dict[str, Any]) -> Any:
            # LangChain calls _run(**tool_input) for a mapping input, but some
            # paths pass the mapping positionally — accept both.
            call_kwargs = dict(kwargs)
            if len(args) == 1 and isinstance(args[0], dict):
                call_kwargs = {**args[0], **call_kwargs}
            elif args:
                call_kwargs["input"] = args[0] if len(args) == 1 else list(args)

            return _record_mock_call(self.scrutineer_mock, self.scrutineer_trace, call_kwargs)


def build_mock_tool(mock: MockTool, trace: AgentTrace) -> Any:
    """Build a real LangChain tool backed by ``mock``.

    This is what gets substituted into an agent's tool list. It raises rather
    than returning a stand-in if langchain-core is unavailable, because a
    non-LangChain object in a LangChain agent's tool list does not intercept
    anything.
    """
    if BaseTool is None:
        raise AgentInterceptionError(
            "cannot intercept: langchain-core is not installed, so Scrutineer cannot "
            "build a LangChain tool to substitute for the agent's real one. Install "
            "with `pip install scrutineer-agents[langchain]`, or pass intercept=False "
            "if you only want the adapters."
        )

    return MockBackedTool(
        name=mock.name,
        description=getattr(mock, "description", None) or f"Scrutineer mock tool: {mock.name}",
        scrutineer_mock=mock,
        scrutineer_trace=trace,
    )


class ScrutineerToolAdapter:
    """Wraps a LangChain BaseTool with a scrutineer MockTool.

    Intercepts ``invoke()`` and ``__call__`` on the original tool, delegates
    to the mock tool for response generation, and records every call into
    the provided AgentTrace.

    If ``base_tool`` is None, operates as a standalone mock tool adapter
    (useful for testing without langchain-core installed).

    Args:
        base_tool: The original LangChain BaseTool to wrap. If None, the
                   adapter acts as a standalone callable proxy.
        mock: The scrutineer MockTool that provides canned responses.
        trace: AgentTrace to record all tool calls into.
    """

    def __init__(
        self,
        mock: MockTool,
        trace: AgentTrace,
        base_tool: Any | None = None,
    ) -> None:
        # Validate langchain availability only when a real tool is provided
        if base_tool is not None and BaseTool is not None:
            if not isinstance(base_tool, BaseTool):
                raise TypeError(
                    f"base_tool must be a langchain BaseTool instance, "
                    f"got {type(base_tool).__name__}"
                )

        self._base_tool = base_tool
        self._mock = mock
        self._trace = trace

        # Expose the mock tool's name so callers can identify this adapter
        self.name: str = mock.name

    @property
    def mock(self) -> MockTool:
        """Access the underlying scrutineer MockTool."""
        return self._mock

    @property
    def trace(self) -> AgentTrace:
        """Access the AgentTrace this adapter records into."""
        return self._trace

    def invoke(self, input: Any = None, **kwargs: Any) -> Any:
        """Invoke the tool, delegating to the mock and recording the call.

        Compatible with LangChain's ``BaseTool.invoke()`` interface:
        ``invoke(input, config=None, **kwargs)``.

        If a real BaseTool is present, its ``invoke`` is called to preserve
        any input parsing/validation it performs. Otherwise, the mock is
        called directly with ``**kwargs``.

        Returns the mock tool's response (or raises its configured error).
        """
        # Merge input into kwargs if it's a dict
        call_kwargs = dict(kwargs)
        if isinstance(input, dict):
            call_kwargs.update(input)
        elif input is not None:
            # Non-dict input: pass as 'input' kwarg (LangChain convention)
            call_kwargs["input"] = input

        return self._call_mock(call_kwargs)

    def __call__(self, **kwargs: Any) -> Any:
        """Direct call interface — delegates to mock and records the call."""
        return self._call_mock(kwargs)

    def _call_mock(self, kwargs: dict[str, Any]) -> Any:
        """Execute the mock tool and record the call into the trace."""
        return _record_mock_call(self._mock, self._trace, kwargs)

    def reset_calls(self) -> None:
        """Clear recorded calls on the mock tool."""
        self._mock.calls.clear()

    # ──────────────────────────────────────────────────────
    # Duck-typing for LangChain BaseTool compatibility
    # ──────────────────────────────────────────────────────

    @property
    def description(self) -> str:
        """Tool description — from the base tool or default."""
        if self._base_tool is not None:
            return getattr(self._base_tool, "description", self.name)
        return f"Scrutineer mock tool: {self.name}"

    @property
    def args(self) -> dict[str, Any]:
        """Tool argument schema — from the base tool or empty."""
        if self._base_tool is not None:
            return getattr(self._base_tool, "args", {})
        return {}

    def __repr__(self) -> str:
        base = type(self._base_tool).__name__ if self._base_tool else "None"
        return (
            f"ScrutineerToolAdapter(base={base}, "
            f"mock={self._mock.name!r}, "
            f"calls={self._mock.call_count})"
        )


def wrap_agent(
    agent: Any,
    tool_map: dict[str, MockTool],
    trace: AgentTrace,
    intercept: bool = True,
) -> AgentWrapper:
    """Wrap an entire LangChain agent, replacing its tools with mocks.

    Creates a wrapper around the agent that:
    1. Intercepts all tool calls through scrutineer MockTools
    2. Records every call into the AgentTrace
    3. Preserves the agent's ``invoke`` / ``__call__`` interface

    By default this **rebinds the agent's tools in place**: every entry in
    ``agent.tools`` whose name appears in ``tool_map`` is replaced with a
    mock-backed LangChain tool, so the agent's own call path reaches the mock.
    Tools Scrutineer does not have a mock for are left alone (and listed on
    ``AgentWrapper.unintercepted_tools``) — those can still reach the real
    world, so pass a mock for every tool you need to contain.

    If the agent's tools cannot be rebound, this raises
    ``AgentInterceptionError`` rather than wrapping the agent in a no-op that
    delegates to real tools while reporting success. Agents whose tools are
    bound internally (for example a ``create_react_agent`` Runnable) should be
    built against ``wrapper.tools`` instead.

    Args:
        agent: A LangChain agent exposing a rebindable ``tools`` list.
        tool_map: Mapping of tool name → scrutineer MockTool.
        trace: AgentTrace to record all calls into.
        intercept: Set False to build the adapters without touching the agent
            (explicit opt-in for adapter-only use; the agent keeps its real
            tools).

    Returns:
        AgentWrapper that behaves like the original agent but routes
        tool calls through scrutineer.

    Raises:
        AgentInterceptionError: ``intercept`` is True and the agent's tools
            could not be replaced.

    Example:
        agent = create_react_agent(model, tools, prompt)
        wrapped = wrap_agent(
            agent=agent,
            tool_map={
                "search": MockTool("search", response=SEARCH_RESULTS),
                "email": MockTool("email", response="sent"),
            },
            trace=trace,
        )
        result = wrapped.invoke({"messages": [...]})
    """
    return AgentWrapper(
        agent=agent,
        tool_map=tool_map,
        trace=trace,
        intercept=intercept,
    )


class AgentWrapper:
    """Wraps a LangChain agent with scrutineer tool mocking.

    This wrapper intercepts the agent's tool execution path and replaces
    all tool calls with scrutineer MockTools. The agent's core LLM reasoning
    loop is untouched — only the tool layer is replaced.

    Replacement happens by rebinding the agent's ``tools`` list in place, so
    it works for any agent that keeps its tools there. Agents that bind tools
    internally must be constructed against ``AgentWrapper.tools`` instead.

    The wrapper implements both ``invoke()`` and ``__call__()`` for
    compatibility with different LangChain usage patterns.
    """

    def __init__(
        self,
        agent: Any,
        tool_map: dict[str, MockTool],
        trace: AgentTrace,
        intercept: bool = True,
    ) -> None:
        self._agent = agent
        self._trace = trace
        self._adapters: dict[str, ScrutineerToolAdapter] = {}
        self._tools: dict[str, Any] = {}
        self._unintercepted: list[str] = []

        # Create an adapter (and a real, substitutable tool) per mock tool
        for name, mock in tool_map.items():
            self._adapters[name] = ScrutineerToolAdapter(
                mock=mock,
                trace=trace,
            )
            if intercept:
                self._tools[name] = build_mock_tool(mock, trace)

        if intercept and self._adapters:
            self._rebind_agent_tools()

    def _rebind_agent_tools(self) -> None:
        """Replace the agent's own tools with mock-backed tools, in place.

        Raises:
            AgentInterceptionError: the agent exposes no ``tools`` list, or
                none of the mocked tools are present on it. Both cases mean
                Scrutineer would intercept nothing while reporting success.
        """
        raw = getattr(self._agent, "tools", None)

        if not isinstance(raw, (list, tuple)):
            raise AgentInterceptionError(
                f"cannot intercept: agent {type(self._agent).__name__} exposes no "
                f"rebindable `tools` list, so Scrutineer cannot replace its tools "
                f"(mocks={sorted(self._adapters)}). Build the agent against the "
                "mocked tools via `wrap_agent(...).tools`, or pass intercept=False "
                "to build the adapters only."
            )

        rebuilt: list[Any] = []
        rebound = 0
        leftover: list[str] = []

        for tool in raw:
            name = getattr(tool, "name", None)
            if isinstance(name, str) and name in self._tools:
                rebuilt.append(self._tools[name])
                rebound += 1
            else:
                rebuilt.append(tool)
                leftover.append(name if isinstance(name, str) else repr(tool))

        if rebound == 0:
            raise AgentInterceptionError(
                f"cannot intercept: none of the mocked tools are present on agent "
                f"{type(self._agent).__name__} (mocks={sorted(self._adapters)}, "
                f"agent tools={leftover}). Scrutineer would leave the real tools in "
                "place and report success."
            )

        setattr(
            self._agent,
            "tools",
            tuple(rebuilt) if isinstance(raw, tuple) else rebuilt,
        )
        self._unintercepted = leftover

    @property
    def adapters(self) -> dict[str, ScrutineerToolAdapter]:
        """Get all tool adapters by name."""
        return dict(self._adapters)

    @property
    def tools(self) -> dict[str, Any]:
        """The mock-backed LangChain tools, for rebuilding an agent against them.

        Use this when the agent's tools cannot be rebound (for example
        ``create_react_agent(model, wrapper.tools.values())``).
        """
        return dict(self._tools)

    @property
    def unintercepted_tools(self) -> list[str]:
        """Names of the agent's tools that were left real (no mock supplied)."""
        return list(self._unintercepted)

    @property
    def trace(self) -> AgentTrace:
        """Access the AgentTrace."""
        return self._trace

    def get_mock(self, name: str) -> MockTool | None:
        """Get the mock tool for a given name."""
        adapter = self._adapters.get(name)
        return adapter.mock if adapter else None

    def invoke(self, input: Any = None, **kwargs: Any) -> Any:
        """Invoke the wrapped agent.

        Delegates to the original agent. Interception happened at wrap time by
        substituting its tools, so the agent's own tool-calling path reaches
        the mocks.

        Returns the agent's response.
        """
        if hasattr(self._agent, "invoke"):
            return self._agent.invoke(input, **kwargs)
        return self._agent(input, **kwargs)

    def __call__(self, **kwargs: Any) -> Any:
        """Call interface — delegates to invoke."""
        return self.invoke(**kwargs)

    def __repr__(self) -> str:
        return (
            f"AgentWrapper(agent={type(self._agent).__name__}, "
            f"tools={list(self._adapters.keys())}, "
            f"unintercepted={self._unintercepted})"
        )
