"""
Scrutineer — Agent Behavioral Testing Platform
Tests what agents DO, not just what they SAY.
"""
from importlib.metadata import PackageNotFoundError as _PackageNotFoundError
from importlib.metadata import version as _package_version

try:  # single source of truth: the installed distribution's metadata
    __version__ = _package_version("scrutineer-agents")
except _PackageNotFoundError:  # source tree with no install (e.g. PYTHONPATH=src)
    __version__ = "0.3.1"

from scrutineer.assertions import (
    assert_agent_recovers,
    assert_chaos_resilience,
    assert_graceful_degradation,
    assert_latency,
    assert_no_silent_failure,
    assert_no_tool_errors,
    assert_state_changed,
    assert_state_consistent,
    assert_state_consistent_across_traces,
    assert_state_no_collisions,
    assert_state_not_stale,
    assert_step_count,
    assert_token_usage,
    assert_tool_call_count,
    assert_tool_call_order,
    assert_tool_called,
    assert_tool_latency,
    assert_tool_not_called,
    detect_state_collisions,
)
from scrutineer.baseline import (
    BaselineMetadata,
    delete_baseline,
    list_baselines,
    load_baseline,
    record_baseline,
)
from scrutineer.chaos import (
    CascadingFailures,
    ChaosBudget,
    ChaosBudgetExhausted,
    ContextDegradation,
    DegradationStrategy,
    DriftIntensity,
    SpecDrift,
    inject_failures,
)
from scrutineer.chaos_presets import PRESETS, list_presets, load_preset
from scrutineer.env import (
    Environment,
    EnvironmentBuilder,
    MockAPI,
    MockDatabase,
    MockTool,
    MockToolCall,
    MockToolError,
    RateLimitError,
    TimeoutError,
)
from scrutineer.models import AgentTrace, Step, StepAction, ToolCall
from scrutineer.otel import (
    OTelSpan,
    SpanAttribute,
    SpanEvent,
    export_to_otel,
    trace_to_spans,
)
from scrutineer.reporting import (
    RegressionReport,
    ResultDelta,
    ScenarioDelta,
    build_regression_report,
    diff_traces,
    generate_html_report,
    generate_junit_xml,
    generate_junit_xml_from_report,
)
from scrutineer.runner import (
    AgentConfig,
    ScenarioRunner,
    ScrutineerResult,
    ScrutineerScenario,
    TestResult,
    TestScenario,
    scrutineer_test,
)

__all__ = [
    # Env
    "Environment",
    "EnvironmentBuilder",
    "MockAPI",
    "MockDatabase",
    "MockTool",
    "MockToolCall",
    "MockToolError",
    "RateLimitError",
    "TimeoutError",
    # Models
    "AgentTrace",
    "ToolCall",
    "Step",
    "StepAction",
    # Runner
    "AgentConfig",
    "ScenarioRunner",
    "ScrutineerResult",
    "ScrutineerScenario",
    "TestResult",
    "TestScenario",
    "scrutineer_test",
    # Assertions
    "assert_tool_called",
    "assert_tool_not_called",
    "assert_tool_call_order",
    "assert_tool_call_count",
    "assert_no_tool_errors",
    "assert_state_consistent",
    "assert_state_changed",
    "assert_graceful_degradation",
    "assert_no_silent_failure",
    "assert_chaos_resilience",
    "assert_agent_recovers",
    "assert_latency",
    "assert_token_usage",
    "assert_step_count",
    "assert_tool_latency",
    "assert_state_not_stale",
    "assert_state_consistent_across_traces",
    "detect_state_collisions",
    "assert_state_no_collisions",
    # Chaos
    "ChaosBudget",
    "ChaosBudgetExhausted",
    "ContextDegradation",
    "CascadingFailures",
    "SpecDrift",
    "DegradationStrategy",
    "DriftIntensity",
    "inject_failures",
    # Chaos Presets
    "PRESETS",
    "load_preset",
    "list_presets",
    # Reporting
    "RegressionReport",
    "ScenarioDelta",
    "ResultDelta",
    "build_regression_report",
    "diff_traces",
    "generate_html_report",
    "generate_junit_xml",
    "generate_junit_xml_from_report",
    # OTel
    "OTelSpan",
    "SpanAttribute",
    "SpanEvent",
    "trace_to_spans",
    "export_to_otel",
    # Baseline
    "BaselineMetadata",
    "record_baseline",
    "load_baseline",
    "list_baselines",
    "delete_baseline",
]
