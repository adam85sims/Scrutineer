"""The documented JSON workflow, end to end.

The package README tells a reader to run

    scrutineer-run run --all --json-output > results.json
    scrutineer-run baseline record v1.2.3 --path results.json

Both halves were broken, in different ways, and neither was caught by the suite:

* the flag is advertised as "Machine-readable JSON output", but the progress and summary lines
  shared stdout with the document, so `> results.json` produced a file that was not JSON;
* even once stdout was pure, `baseline record` raised `KeyError: 'assertion_name'` — the emitter
  writes `name`/`error`, the deserializer demanded `assertion_name`/`error_message`.

These tests run the two halves in order, which is the only way either defect shows up.
"""

from __future__ import annotations

import json

import pytest
from click.testing import CliRunner

from scrutineer.cli import cli

PASSING_SCENARIO = """\
id: roundtrip-demo
name: Roundtrip demo
task: call the search tool
env_config:
  tools:
    search:
      response:
        results:
          - found
agent:
  type: script
  steps:
    - tool: search
      args:
        query: refund policy
assertions:
  - type: tool_called
    tool: search
  - type: tool_called
    tool: missing    # deliberately fails, so the assertion NAME must survive the round trip
"""


@pytest.fixture
def project(tmp_path, monkeypatch):
    """A project directory containing one scenario, with baselines redirected to tmp."""
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    (scenarios / "demo.yaml").write_text(PASSING_SCENARIO)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_json_output_puts_json_on_stdout_and_nothing_else(project, monkeypatch):
    """"Machine-readable" has to mean the document is the whole of stdout."""
    result = CliRunner().invoke(cli, ["run", "--all", "--json-output"])

    document = json.loads(result.stdout)  # raises if any human line leaked in

    assert document["total"] == 1
    assert document["passed"] == 0  # the second assertion is designed to fail
    assert result.stderr, "the human-facing progress should still be reported on stderr"


def test_json_output_round_trips_into_a_baseline(project, tmp_baseline_dir):
    """The second documented command must accept the first command's output."""
    runner = CliRunner()
    run_result = runner.invoke(cli, ["run", "--all", "--json-output"])
    assert run_result.exit_code == 1, run_result.output  # a scenario failed, as designed

    results_file = project / "results.json"
    results_file.write_text(run_result.stdout)

    record = runner.invoke(cli, ["baseline", "record", "v1", "--path", str(results_file)])

    assert record.exit_code == 0, record.output
    assert "Baseline 'v1' recorded" in record.stdout


def test_assertion_names_and_failure_reasons_survive_the_round_trip(project, tmp_baseline_dir):
    """A failure reason that vanishes in serialisation is a silently weakened baseline."""
    runner = CliRunner()
    run_result = runner.invoke(cli, ["run", "--all", "--json-output"])
    results_file = project / "results.json"
    results_file.write_text(run_result.stdout)

    from scrutineer.cli import _deserialize_results_from_json

    raw = json.loads(results_file.read_text())["results"]
    results = _deserialize_results_from_json(raw)

    names = [a.assertion_name for a in results[0].assertion_results]
    assert names == ["tool_called(tool_name='search')", "tool_called(tool_name='missing')"]

    failed = [a for a in results[0].assertion_results if not a.passed]
    assert failed and failed[0].error_message, "the failure reason was lost in serialisation"


def test_json_output_is_still_pure_with_verbose(project):
    """The combination nothing else tested: `--verbose` printed straight to stdout."""
    result = CliRunner().invoke(cli, ["run", "--all", "--json-output", "--verbose"])

    document = json.loads(result.stdout)  # raises if a verbose header leaked into stdout

    assert document["total"] == 1
    assert "[1/1]" in result.stderr, "the verbose headers should have moved to stderr"


def test_json_output_emits_a_document_even_when_nothing_runs(tmp_path, monkeypatch):
    """`> results.json` must always produce JSON, including for an empty directory."""
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["run", "--all", "--json-output"])

    document = json.loads(result.stdout)

    assert document == {
        "total": 0,
        "passed": 0,
        "failed": 0,
        "duration_ms": document["duration_ms"],
        "incomplete": False,
        "discovery_problems": [],
        "results": [],
    }
    assert result.exit_code == 0


def test_baseline_record_rejects_a_non_json_file_without_a_traceback(tmp_path, tmp_baseline_dir):
    """An empty or truncated results file is a user mistake, not a stack trace."""
    results_file = tmp_path / "results.json"
    results_file.write_text("")  # what `> results.json` gives you when the run emitted nothing

    result = CliRunner().invoke(cli, ["baseline", "record", "v1", "--path", str(results_file)])

    assert result.exit_code == 1
    assert "is not valid JSON" in result.output
    assert "Traceback" not in result.output
