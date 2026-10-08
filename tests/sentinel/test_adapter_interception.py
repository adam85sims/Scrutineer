"""Adapter interception tests — the claim that Sentinel can test a real agent.

The readiness assessment (§4.3) found that ``wrap_agent`` created adapters but
never injected them, so ``AgentWrapper.invoke`` delegated to the original agent,
which went on calling its own REAL tools: production side effects, an empty
trace, and a report of success. This module pins the fix:

* a mocked tool IS used and the agent's real tool is NOT,
* the call lands in the trace,
* an agent Sentinel cannot intercept raises rather than silently passing
  real tools through (the "fail open" behaviour is the dangerous part).

These tests need langchain-core for the real ``BaseTool`` objects, so the module
skips without it.
"""

from __future__ import annotations

import pytest

langchain_tools = pytest.importorskip(
    "langchain_core.tools", reason="adapter interception needs langchain-core"
)

from langchain_core.tools import StructuredTool  # noqa: E402

from sentinel.adapters.langchain import (  # noqa: E402
    AgentInterceptionError,
    wrap_agent,
)
from sentinel.env import MockTool  # noqa: E402
from sentinel.models import AgentTrace  # noqa: E402


class _ToolCallingAgent:
    """A stand-in agent whose ``invoke`` calls its own tools, like a real one.

    Not an LLM agent — it exists so the test can observe *which* tool object the
    agent's call path actually reaches. That is the variable under test.
    """

    def __init__(self, tools: list) -> None:
        self.tools = list(tools)

    def invoke(self, input, **kwargs):  # noqa: A002
        return {tool.name: tool.invoke({"query": "policies"}) for tool in self.tools}


def _real_tool(counter: dict) -> StructuredTool:
    """A tool that records every time the REAL implementation is reached."""

    def search(query: str) -> str:
        counter["real_calls"] += 1
        return "REAL NETWORK RESULT"

    return StructuredTool.from_function(
        func=search, name="search", description="Real search tool"
    )


class TestWrappedAgentIntercepts:
    def test_mock_is_used_and_real_tool_is_never_called(self):
        """The whole product claim: the real tool must not run."""
        counter = {"real_calls": 0}
        agent = _ToolCallingAgent([_real_tool(counter)])
        trace = AgentTrace()
        mock = MockTool("search", response={"results": ["mocked"]})

        wrapper = wrap_agent(agent=agent, tool_map={"search": mock}, trace=trace)
        result = wrapper.invoke({"messages": ["look up the refund policy"]})

        assert counter["real_calls"] == 0, (
            "the agent's REAL tool was called — interception failed and the "
            "run would have produced production side effects"
        )
        assert mock.call_count == 1, "the mock tool was never used"
        assert result == {"search": {"results": ["mocked"]}}

    def test_intercepted_call_is_recorded_in_the_trace(self):
        """A trace with no tool calls is how the old bug reported success."""
        counter = {"real_calls": 0}
        agent = _ToolCallingAgent([_real_tool(counter)])
        trace = AgentTrace()
        mock = MockTool("search", response={"results": ["mocked"]})

        wrapper = wrap_agent(agent=agent, tool_map={"search": mock}, trace=trace)
        wrapper.invoke({"messages": ["look up the refund policy"]})

        assert len(trace.tool_calls) == 1, "the call was not recorded"
        assert trace.tool_calls[0].tool_name == "search"
        assert trace.tool_calls[0].arguments == {"query": "policies"}

    def test_unmocked_agent_tools_are_reported_not_hidden(self):
        """Tools left real must be visible, not silently passed through."""
        counter = {"real_calls": 0}
        other = StructuredTool.from_function(
            func=lambda q: "unmocked", name="email", description="Real email tool"
        )
        agent = _ToolCallingAgent([_real_tool(counter), other])
        trace = AgentTrace()

        wrapper = wrap_agent(
            agent=agent, tool_map={"search": MockTool("search")}, trace=trace
        )

        assert wrapper.unintercepted_tools == ["email"]


    def test_intercept_false_leaves_the_real_tool_in_place(self):
        """Negative control: the one-line difference must flip the verdict.

        Without this, the interception tests above could pass against a
        Sentinel that intercepts nothing — which is exactly the bug they exist
        to catch.
        """
        counter = {"real_calls": 0}
        agent = _ToolCallingAgent([_real_tool(counter)])
        trace = AgentTrace()
        mock = MockTool("search", response={"results": ["mocked"]})

        wrapper = wrap_agent(
            agent=agent,
            tool_map={"search": mock},
            trace=trace,
            intercept=False,
        )
        result = wrapper.invoke({"messages": ["look up the refund policy"]})

        assert counter["real_calls"] == 1, "with interception off, the real tool is what runs"
        assert mock.call_count == 0
        assert trace.tool_calls == []
        assert result == {"search": "REAL NETWORK RESULT"}


class TestFailClosed:
    def test_uninterceptable_agent_raises(self):
        """No rebindable tool list => raise, never silently pass tools through."""

        class OpaqueAgent:
            """Like a create_react_agent Runnable: tools bound invisibly."""

            def invoke(self, input, **kwargs):  # noqa: A002
                return "real response"

        with pytest.raises(AgentInterceptionError, match="cannot intercept"):
            wrap_agent(
                agent=OpaqueAgent(),
                tool_map={"search": MockTool("search")},
                trace=AgentTrace(),
            )

    def test_empty_tool_map_is_a_no_op(self):
        """Nothing to mock => delegating is correct, not a silent failure."""

        class OpaqueAgent:
            def invoke(self, input, **kwargs):  # noqa: A002
                return "real response"

        wrapper = wrap_agent(agent=OpaqueAgent(), tool_map={}, trace=AgentTrace())
        assert wrapper.invoke({}) == "real response"

    def test_intercept_false_is_an_explicit_opt_out(self):
        """Adapter-only use is allowed, but only by asking for it."""
        trace = AgentTrace()
        wrapper = wrap_agent(
            agent=object(),
            tool_map={"search": MockTool("search", response="ok")},
            trace=trace,
            intercept=False,
        )

        assert "search" in wrapper.adapters
        assert wrapper.unintercepted_tools == []
