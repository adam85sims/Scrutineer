"""
Scrutineer CLI — Command-line interface for running scrutineer tests.

Usage:
    scrutineer-run run --scenario <name> [--verbose]
    scrutineer-run run --all [--verbose]
    scrutineer-run run --path <scenario-file> [--verbose]
    scrutineer-run baseline record <label> [--path results.json]
    scrutineer-run baseline list
    scrutineer-run baseline show <label>
    scrutineer-run diff <baseline1> <baseline2>
    scrutineer-run report --baseline <label> [--format html|junit] [--output file]
    scrutineer-run run --help
"""
from __future__ import annotations

import importlib
import json
import os
import shutil
import sys
import time
from pathlib import Path

import click


class ScenarioLoadError(Exception):
    """A scenario file could not be read, for a reason the user must act on.

    Raised instead of returning an empty list, so the CLI reports the true cause once rather
    than printing a second, wrong one after it.
    """


def _examples_source_dir() -> Path:
    """Locate the starter kit that ships with Scrutineer.

    Installed from a wheel or an sdist it is ``scrutineer/examples``. Running from a source
    checkout (an editable install), the package directory is ``src/scrutineer`` and the kit is
    the repo-root ``examples/`` — the same files, force-included into the wheel at build time
    by ``[tool.hatch.build.targets.wheel.force-include]``.
    """
    bundled = Path(__file__).resolve().parent / "examples"
    if bundled.is_dir():
        return bundled

    checkout = Path(__file__).resolve().parents[2] / "examples"
    if checkout.is_dir():
        return checkout

    raise ScenarioLoadError(
        "could not find the bundled example scenarios — this is a packaging bug, "
        "reinstall scrutineer-agents"
    )


@click.group()
@click.version_option(package_name="scrutineer-agents")
def cli() -> None:
    """Scrutineer — Agent Behavioral Testing Platform.

    Run behavioral tests against agents to verify what they DO,
    not just what they SAY.
    """


# ──────────────────────────────────────────────────────
# scrutineer run
# ──────────────────────────────────────────────────────


@cli.command()
@click.option(
    "--scenario",
    required=False,
    help="Name of the test scenario to run.",
)
@click.option(
    "--all",
    "run_all",
    is_flag=True,
    default=False,
    help="Run all discovered scenarios.",
)
@click.option(
    "--path",
    "scenario_path",
    type=click.Path(exists=True),
    required=False,
    help="Path to a scenario file (JSON or YAML).",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Enable verbose output with detailed test results.",
)
@click.option(
    "--json-output",
    is_flag=True,
    default=False,
    help="Output results as JSON.",
)
def run(
    scenario: str | None,
    run_all: bool,
    scenario_path: str | None,
    verbose: bool,
    json_output: bool,
) -> None:
    """Run scrutineer test scenarios.

    \b
    Examples:
        scrutineer-run run --scenario injection-resistance
        scrutineer-run run --scenario tool-abuse --verbose
        scrutineer-run run --all --verbose
        scrutineer-run run --path scenarios/refund_agent.json
    """
    from scrutineer.runner import ScenarioRunner, TestResult
    from scrutineer.scenario_schema import ScenarioSchemaError

    runner = ScenarioRunner()

    # With --json-output the machine-readable document IS the contract, so every human-facing
    # line moves to stderr and stdout carries JSON and nothing else. The documented workflow
    # (`scrutineer run --all --json-output > results.json`, then
    # `scrutineer baseline record LABEL --path results.json`) cannot work while the progress and
    # summary lines share stdout with the document.
    def emit(message: str = "") -> None:
        click.echo(message, err=json_output)

    # Collect scenarios to run
    scenarios = []
    discovery_problems: list[str] = []

    if scenario_path:
        # Load from file
        try:
            scenarios = _load_scenario_file(scenario_path)
        except ScenarioLoadError as exc:
            click.echo(f"[scrutineer] ERROR: {exc}", err=True)
            sys.exit(1)
        if not scenarios:
            click.echo("[scrutineer] ERROR: No scenarios found in file.", err=True)
            sys.exit(1)
    elif scenario:
        # Load specific scenario by name from discovery
        found, _ = _discover_or_report()
        match = [s for s in found if s.id == scenario or s.name == scenario]
        if not match:
            click.echo(
                f"[scrutineer] ERROR: Scenario '{scenario}' not found.\n"
                f"Available: {', '.join(s.id for s in found)}",
                err=True,
            )
            sys.exit(1)
        scenarios = match
    elif run_all:
        scenarios, discovery_problems = _discover_or_report()
        # "Nothing to run" is only a clean exit when nothing was *missed*, either. With a
        # problem outstanding, fall through so the incompleteness check below can speak; with
        # --json-output, fall through too, so stdout still carries a document rather than nothing.
        if not scenarios and not discovery_problems and not json_output:
            click.echo("[scrutineer] No scenarios discovered.", err=True)
            sys.exit(0)
    else:
        click.echo(
            "[scrutineer] ERROR: Specify --scenario, --all, or --path.\n"
            "Run 'scrutineer-run run --help' for usage.",
            err=True,
        )
        sys.exit(1)

    # Execute scenarios
    emit(f"[scrutineer] Running {len(scenarios)} scenario(s)...\n")

    results: list[TestResult] = []
    start_time = time.time()

    for i, scenario in enumerate(scenarios, 1):
        if verbose:
            emit(f"  [{i}/{len(scenarios)}] {scenario.name}")
            emit(f"    Task: {scenario.task}")
            emit(f"    Tags: {', '.join(scenario.tags) if scenario.tags else 'none'}")

        try:
            result = runner.run(scenario)
        except ScenarioSchemaError as exc:
            result = TestResult(
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                passed=False,
                error=f"Invalid scenario: {exc}",
            )
        except (ValueError, TypeError) as exc:
            # Raised by _build_env / _apply_chaos for malformed env or chaos blocks.
            result = TestResult(
                scenario_id=scenario.id,
                scenario_name=scenario.name,
                passed=False,
                error=f"Invalid scenario: {exc}",
            )
        results.append(result)

        # result.summary already carries the [PASS]/[FAIL] tag.
        emit(f"  {result.summary}")

        # Failure reasons are always shown: a test runner that hides why something
        # failed is worse than useless.
        if not result.passed:
            for a in result.failed_assertions():
                emit(f"      ✗ {a.assertion_name}: {a.error_message}")
            if result.error and not result.failed_assertions():
                emit(f"      ! {result.error}")

        if verbose:
            emit()

    # Summary
    total_time = (time.time() - start_time) * 1000
    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed

    emit("─" * 60)
    emit(
        f"[scrutineer] {len(results)} scenario(s): "
        f"{passed} passed, {failed} failed "
        f"({total_time:.0f}ms total)"
    )

    if json_output:
        output = {
            "total": len(results),
            "passed": passed,
            "failed": failed,
            "duration_ms": total_time,
            # Never let the document look complete when part of the directory went unread: a
            # consumer keying on total/passed would otherwise see a clean run over a subset.
            "incomplete": bool(discovery_problems),
            "discovery_problems": list(discovery_problems),
            "results": [
                {
                    "scenario_id": r.scenario_id,
                    "scenario_name": r.scenario_name,
                    "passed": r.passed,
                    "duration_ms": r.duration_ms,
                    "assertion_results": [
                        {
                            "name": a.assertion_name,
                            "passed": a.passed,
                            "error": a.error_message,
                        }
                        for a in r.assertion_results
                    ],
                    "error": r.error,
                }
                for r in results
            ],
        }
        click.echo(json.dumps(output, indent=2))

    if discovery_problems:
        # A run that could not read every scenario in the directory is not a complete run, and
        # reporting "all passed" over a subset is the exact failure this product exists to find
        # in other people's systems. Report it, and exit non-zero even when nothing failed.
        click.echo(
            f"[scrutineer] ERROR: {len(discovery_problems)} file(s) under the scenario "
            f"directories could not be read — this run is incomplete.",
            err=True,
        )
        sys.exit(1)

    if failed > 0:
        sys.exit(1)


# ──────────────────────────────────────────────────────
# scrutineer init
# ──────────────────────────────────────────────────────


@cli.command()
@click.option(
    "--dir",
    "target_dir",
    type=click.Path(file_okay=False),
    default=".",
    show_default=True,
    help="Directory to write the starter kit into.",
)
@click.option("--force", is_flag=True, help="Replace an existing starter kit.")
def init(target_dir: str, force: bool) -> None:
    """Write the starter scenarios, so there is something to run straight away.

    \b
    Examples:
        scrutineer init
        scrutineer init --dir ./agent-tests
        scrutineer init --force

    Copies the scenarios that ship inside the package into
    ``<dir>/scrutineer-examples/`` and prints the commands to run them.
    """
    source = _examples_source_dir()
    destination = Path(target_dir).resolve() / "scrutineer-examples"

    if destination == source or source in destination.parents:
        click.echo(
            f"[scrutineer] ERROR: refusing to copy the starter kit into itself ({destination}).",
            err=True,
        )
        sys.exit(1)

    if destination.exists():
        if not force:
            click.echo(
                f"[scrutineer] ERROR: {destination} already exists — not overwriting it.\n"
                f"Re-run with --force to replace it, or pass --dir to write elsewhere.",
                err=True,
            )
            sys.exit(1)
        shutil.rmtree(destination)

    shutil.copytree(source, destination)

    written = sum(1 for path in destination.rglob("*") if path.is_file())
    shown = Path(target_dir) / "scrutineer-examples"

    click.echo(f"[scrutineer] Wrote {written} file(s) to {destination}\n")
    click.echo("Run one now:")
    click.echo(f"  scrutineer run --path {shown}/basic_scenario.yaml")
    click.echo(f"  scrutineer run --path {shown}/chaos_scenario.yaml")
    click.echo(
        f"  scrutineer run --path {shown}/chaos_scenario_unhandled.yaml"
        f"   # FAILS on purpose"
    )


# ──────────────────────────────────────────────────────
# scrutineer list
# ──────────────────────────────────────────────────────


@cli.command(name="list")
def list_scenarios() -> None:
    """List all discovered test scenarios."""
    scenarios, _ = _discover_or_report()
    if not scenarios:
        click.echo("[scrutineer] No scenarios discovered.")
        return

    click.echo(f"[scrutineer] Found {len(scenarios)} scenario(s):\n")
    for s in scenarios:
        tags = ", ".join(s.tags) if s.tags else "no tags"
        click.echo(f"  {s.id}: {s.name}")
        if s.description:
            click.echo(f"    {s.description}")
        click.echo(f"    Tags: {tags}")
        click.echo()


# ──────────────────────────────────────────────────────
# scrutineer info
# ──────────────────────────────────────────────────────


@cli.command()
@click.argument("scenario_id")
def info(scenario_id: str) -> None:
    """Show detailed info about a specific scenario."""
    scenarios, _ = _discover_or_report()
    match = [s for s in scenarios if s.id == scenario_id]
    if not match:
        click.echo(f"[scrutineer] ERROR: Scenario '{scenario_id}' not found.", err=True)
        sys.exit(1)

    s = match[0]
    click.echo(f"Scenario: {s.id}")
    click.echo(f"  Name: {s.name}")
    click.echo(f"  Description: {s.description or '(none)'}")
    click.echo(f"  Task: {s.task or '(none)'}")
    click.echo(f"  Tags: {', '.join(s.tags) if s.tags else 'none'}")
    click.echo(f"  Timeout: {s.timeout_seconds}s")
    click.echo(f"  Assertions: {len(s.assertions)}")


# ──────────────────────────────────────────────────────
# scrutineer baseline (group)
# ──────────────────────────────────────────────────────


@cli.group()
def baseline() -> None:
    """Manage test baselines — record, list, show, delete."""
    pass


@baseline.command("record")
@click.argument("label")
@click.option("--path", "results_path", type=click.Path(exists=True),
              help="Path to results JSON file (from scrutineer run --json-output).")
@click.option("--tag", "tags", multiple=True, help="Tag(s) for this baseline (repeatable).")
@click.option("--description", "-d", default="", help="Description of this baseline.")
def baseline_record(
    label: str,
    results_path: str | None,
    tags: tuple[str, ...],
    description: str,
) -> None:
    """Record a baseline from results.

    \b
    Examples:
        scrutineer-run baseline record v1.2.3 --path results.json
        scrutineer-run baseline record nightly --tag ci --tag nightly
    """
    from scrutineer.baseline import record_baseline

    if results_path:
        # Load results from JSON file
        try:
            with open(results_path) as f:
                raw = json.load(f)
        except json.JSONDecodeError as exc:
            # A truncated or empty results file is a user-facing mistake, not a traceback.
            click.echo(
                f"[scrutineer] ERROR: '{results_path}' is not valid JSON ({exc}).\n"
                f"  Produce it with: scrutineer run --all --json-output > results.json",
                err=True,
            )
            sys.exit(1)

        # If it's the scrutineer run --json-output format, extract results
        if isinstance(raw, dict) and "results" in raw:
            raw = raw["results"]

        results = _deserialize_results_from_json(raw)
    else:
        # Try to read from stdin (pipe support)
        if not sys.stdin.isatty():
            raw = json.load(sys.stdin)
            if isinstance(raw, dict) and "results" in raw:
                raw = raw["results"]
            results = _deserialize_results_from_json(raw)
        else:
            click.echo(
                "[scrutineer] ERROR: Provide results via --path or pipe JSON to stdin.\n"
                "  scrutineer-run run --all --json-output | scrutineer-run baseline record my-label",
                err=True,
            )
            sys.exit(1)

    # Detect git info
    git_sha, git_branch = _detect_git_info()

    path = record_baseline(
        results=results,
        label=label,
        tags=list(tags),
        description=description,
        git_sha=git_sha,
        git_branch=git_branch,
    )
    click.echo(f"[scrutineer] Baseline '{label}' recorded at {path}")
    click.echo(f"  Scenarios: {len(results)}, Passed: {sum(1 for r in results if r.passed)}")


@baseline.command("list")
def baseline_list() -> None:
    """List all recorded baselines."""
    from scrutineer.baseline import list_baselines

    labels = list_baselines()
    if not labels:
        click.echo("[scrutineer] No baselines recorded.")
        return

    click.echo(f"[scrutineer] {len(labels)} baseline(s):\n")
    for label in labels:
        # Load metadata for display
        try:
            from scrutineer.baseline import load_baseline
            meta, _ = load_baseline(label)
            tags_str = f" [{', '.join(meta.tags)}]" if meta.tags else ""
            ts = time.strftime("%Y-%m-%d %H:%M", time.localtime(meta.timestamp))
            click.echo(
                f"  {label}{tags_str} — {meta.scenario_count} scenarios, "
                f"{meta.pass_count} pass, {meta.fail_count} fail ({ts})"
            )
        except Exception:
            click.echo(f"  {label}")


@baseline.command("show")
@click.argument("label")
def baseline_show(label: str) -> None:
    """Show details of a specific baseline."""
    from scrutineer.baseline import load_baseline

    try:
        meta, results = load_baseline(label)
    except FileNotFoundError as e:
        click.echo(f"[scrutineer] ERROR: {e}", err=True)
        sys.exit(1)

    click.echo(f"Baseline: {meta.label}")
    click.echo(f"  Timestamp: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(meta.timestamp))}")
    if meta.git_sha:
        click.echo(f"  Git: {meta.git_sha[:8]} ({meta.git_branch})")
    if meta.tags:
        click.echo(f"  Tags: {', '.join(meta.tags)}")
    if meta.description:
        click.echo(f"  Description: {meta.description}")
    click.echo(f"  Scenarios: {meta.scenario_count} ({meta.pass_count} pass, {meta.fail_count} fail)")
    click.echo()

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        click.echo(f"  [{status}] {r.summary}")


@baseline.command("delete")
@click.argument("label")
def baseline_delete(label: str) -> None:
    """Delete a baseline by label."""
    from scrutineer.baseline import delete_baseline

    if delete_baseline(label):
        click.echo(f"[scrutineer] Baseline '{label}' deleted.")
    else:
        click.echo(f"[scrutineer] ERROR: Baseline '{label}' not found.", err=True)
        sys.exit(1)


# ──────────────────────────────────────────────────────
# scrutineer diff
# ──────────────────────────────────────────────────────


@cli.command()
@click.argument("baseline1")
@click.argument("baseline2")
@click.option("--json-output", is_flag=True, help="Output as JSON.")
def diff(baseline1: str, baseline2: str, json_output: bool) -> None:
    """Compare two baselines and show regressions/fixes.

    \b
    Examples:
        scrutineer-run diff v1.2.3 v1.3.0
        scrutineer-run diff main-abc1234 main-def5678 --json-output
    """
    from scrutineer.baseline import load_baseline
    from scrutineer.reporting import build_regression_report

    try:
        meta1, results1 = load_baseline(baseline1)
    except FileNotFoundError as e:
        click.echo(f"[scrutineer] ERROR: {e}", err=True)
        sys.exit(1)

    try:
        meta2, results2 = load_baseline(baseline2)
    except FileNotFoundError as e:
        click.echo(f"[scrutineer] ERROR: {e}", err=True)
        sys.exit(1)

    report = build_regression_report(
        baseline_results=results1,
        current_results=results2,
        baseline_label=baseline1,
        current_label=baseline2,
        metadata={"baseline1_timestamp": meta1.timestamp, "baseline2_timestamp": meta2.timestamp},
    )

    if json_output:
        click.echo(json.dumps(report.to_dict(), indent=2))
        return

    # Human-readable output
    click.echo(f"\n[diff] Comparing {baseline1} → {baseline2}\n")
    click.echo(f"  Verdict: {report.verdict}")
    click.echo(f"  {report.summary}\n")

    if report.regressions:
        click.echo("  REGRESSIONS:")
        for d in report.regressions:
            click.echo(f"    ✗ {d.scenario_name} ({d.scenario_id})")
            if d.new_failures:
                for f in d.new_failures:
                    click.echo(f"      New failure: {f}")
        click.echo()

    if report.fixes:
        click.echo("  FIXES:")
        for d in report.fixes:
            click.echo(f"    ✓ {d.scenario_name} ({d.scenario_id})")
            if d.fixed_assertions:
                for f in d.fixed_assertions:
                    click.echo(f"      Fixed: {f}")
        click.echo()

    if report.still_failing:
        click.echo("  STILL FAILING:")
        for d in report.still_failing:
            click.echo(f"    ✗ {d.scenario_name} ({d.scenario_id})")
        click.echo()

    if report.new_scenarios:
        click.echo("  NEW SCENARIOS:")
        for d in report.new_scenarios:
            status = "PASS" if d.current_passed else "FAIL"
            click.echo(f"    [{status}] {d.scenario_name} ({d.scenario_id})")
        click.echo()


# ──────────────────────────────────────────────────────
# scrutineer report
# ──────────────────────────────────────────────────────


@cli.command()
@click.option("--baseline", "baseline_label", required=True, help="Baseline label to generate report for.")
@click.option("--format", "report_format", type=click.Choice(["html", "junit", "both"]),
              default="both", help="Report format.")
@click.option("--output", "-o", "output_dir", type=click.Path(), default=".",
              help="Output directory for report files.")
def report(baseline_label: str, report_format: str, output_dir: str) -> None:
    """Generate HTML and/or JUnit reports from a baseline.

    \b
    Examples:
        scrutineer-run report --baseline v1.2.3
        scrutineer-run report --baseline nightly --format html --output ./reports
        scrutineer-run report --baseline v1.3.0 --format junit -o .
    """
    from scrutineer.baseline import load_baseline
    from scrutineer.reporting import generate_html_report, generate_junit_xml

    try:
        meta, results = load_baseline(baseline_label)
    except FileNotFoundError as e:
        click.echo(f"[scrutineer] ERROR: {e}", err=True)
        sys.exit(1)

    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    if report_format in ("html", "both"):
        # Build a simple RegressionReport from just these results
        # (no baseline comparison — single-run report)
        from scrutineer.reporting import RegressionReport, ResultDelta, ScenarioDelta

        deltas = []
        for r in results:
            delta = ResultDelta.STILL_PASS if r.passed else ResultDelta.STILL_FAIL
            deltas.append(
                ScenarioDelta(
                    scenario_id=r.scenario_id,
                    scenario_name=r.scenario_name,
                    delta=delta,
                    current_passed=r.passed,
                    current_duration_ms=r.duration_ms,
                )
            )

        report_obj = RegressionReport(
            baseline_label=baseline_label,
            current_label=baseline_label,
            deltas=deltas,
            metadata=meta.metadata,
        )

        html = generate_html_report(report_obj)
        html_path = out_path / f"scrutineer-report-{baseline_label}.html"
        html_path.write_text(html)
        click.echo(f"[scrutineer] HTML report: {html_path}")

    if report_format in ("junit", "both"):
        xml = generate_junit_xml(results, suite_name=f"scrutineer-{baseline_label}")
        xml_path = out_path / f"scrutineer-report-{baseline_label}.xml"
        xml_path.write_text(xml)
        click.echo(f"[scrutineer] JUnit XML: {xml_path}")


# ──────────────────────────────────────────────────────
# scrutineer trace (OTel export)
# ──────────────────────────────────────────────────────


@cli.command()
@click.argument("baseline_label")
@click.option("--output", "-o", "output_path", type=click.Path(), default=None,
              help="Output file path (default: stdout as JSON).")
@click.option("--endpoint", default=None,
              help="OTLP collector endpoint for live export.")
def trace(baseline_label: str, output_path: str | None, endpoint: str | None) -> None:
    """Export baseline traces as OpenTelemetry spans.

    \b
    Examples:
        scrutineer-run trace v1.2.3                          # JSON to stdout
        scrutineer-run trace v1.2.3 -o traces.json          # JSON to file
        scrutineer-run trace v1.2.3 --endpoint localhost:4317  # live OTLP export
    """
    from scrutineer.baseline import load_baseline
    from scrutineer.otel import trace_to_spans

    try:
        meta, results = load_baseline(baseline_label)
    except FileNotFoundError as e:
        click.echo(f"[scrutineer] ERROR: {e}", err=True)
        sys.exit(1)

    all_spans = []
    for r in results:
        spans = trace_to_spans(
            r.trace,
            service_name=f"scrutineer.{r.scenario_id}",
        )
        all_spans.extend(spans)

    if endpoint:
        # Live export via OTel SDK
        click.echo(f"[scrutineer] Exporting {len(all_spans)} spans to {endpoint}...")
        from scrutineer.otel import export_to_otel

        for r in results:
            ok = export_to_otel(r.trace, service_name=f"scrutineer.{r.scenario_id}", endpoint=endpoint)
            if not ok:
                click.echo("[scrutineer] ERROR: OTel SDK not available. Install opentelemetry-sdk.", err=True)
                sys.exit(1)
        click.echo("[scrutineer] Export complete.")
    else:
        # JSON output
        spans_json = [s.to_dict() for s in all_spans]
        output = json.dumps(spans_json, indent=2)

        if output_path:
            Path(output_path).write_text(output)
            click.echo(f"[scrutineer] {len(all_spans)} spans written to {output_path}")
        else:
            click.echo(output)



# ──────────────────────────────────────────────────────
# scrutineer serve (WebUI)
# ──────────────────────────────────────────────────────


@cli.command()
@click.option("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1).")
@click.option("--port", default=8080, type=int, help="Bind port (default: 8080).")
@click.option("--reload", is_flag=True, default=False, help="Auto-reload on code changes.")
def serve(host: str, port: int, reload: bool) -> None:
    """Start the Scrutineer WebUI dashboard.

    
    Examples:
        scrutineer serve                        # localhost:8080
        scrutineer serve --port 3000            # localhost:3000
        scrutineer serve --host 0.0.0.0 --port 8080  # all interfaces
    """
    try:
        import uvicorn
    except ImportError:
        click.echo(
            "[scrutineer] ERROR: Web dependencies not installed. "
            'Install with: pip install "scrutineer-agents[web]"',
            err=True,
        )
        sys.exit(1)

    click.echo(f"[scrutineer] Starting WebUI at http://{host}:{port}")
    click.echo("[scrutineer] Press Ctrl+C to stop.")

    uvicorn.run(
        "scrutineer.web.app:create_app",
        host=host,
        port=port,
        reload=reload,
        factory=True,
    )


# ──────────────────────────────────────────────────────
# Discovery helpers
# ──────────────────────────────────────────────────────


_SCENARIO_FILE_SUFFIXES = (".yaml", ".yml", ".json")

# Directories under the user's cwd that hold scenario files. `scrutineer init` writes
# `scrutineer-examples/`; `scenarios/` is the conventional home for a project's own files.
_SCENARIO_DIRS = ("scenarios", "scrutineer-examples")

# Subtrees that can never hold a scenario under any layout: compiled Python only.
_SCENARIO_IGNORED_DIRS = frozenset({"__pycache__"})

# Directories that are an installed environment rather than somewhere a user keeps scenarios.
# These are pruned *and reported*. Walking one pulls the packages' own bundled YAML into the run —
# a single `venv/` under `scenarios/` discovered 200 phantom scenarios from scrutineer's own
# packaged examples — and pruning it in silence would hide a real scenario, which is the failure
# an earlier round caught. Reporting keeps the choice visible instead of guessing.
_SCENARIO_ENV_DIRS = frozenset({"node_modules", "site-packages"})

# What a scenario has to contain to count as one. See `_is_scenario_item`.
_SUBSTANTIVE_KEYS = (
    "task",
    "assertions",
    "agent",
    "env_config",
    "chaos",
    "chaos_config",
    "allow_no_assertions",
)


def _is_scenario_item(item: object) -> bool:
    """Is this dict a scenario definition, rather than a config file that happens to be YAML?

    Two ways to qualify, because one test alone fails at one end or the other:

    * **named and diagnostic** — an `id` or `name`, plus one of task / agent / assertions /
      environment / chaos. A docker-compose file, a `package.json`, a GitHub workflow, an
      Ansible playbook and a Grafana dashboard each carry a `name`, and a bare key sniff that
      accepted them made `run --all` execute six infra config files as failing scenarios.
    * **substantive twice over** — two of those blocks without any name. `task: deploy` alone is
      a Taskfile; `task` *and* `assertions` is a scenario, and `_build_scenarios` will happily
      run one with no `id` (defaulting it to "unnamed"), so discovery must not be the stricter
      of the two or it silently drops a file the rest of the system supports.

    This is a heuristic and is documented as one. A marker a user opts into would be better, and
    needs a documented format before it can become the default.
    """
    if not isinstance(item, dict):
        return False

    identified = "id" in item or "name" in item
    substantive = sum(1 for key in _SUBSTANTIVE_KEYS if key in item)
    return (identified and substantive >= 1) or substantive >= 2


def _iter_scenario_items(documents: list) -> list:
    """Flatten parsed documents into candidate items.

    Every document is considered, so a multi-document YAML file is not an error: a k8s-style
    bundle simply yields no scenario items, and two scenarios separated by `---` yield two.
    ``yaml.safe_load`` refuses a multi-document stream outright, which is how one unrelated
    manifest in the scenario directory came to abort every command that discovers scenarios.
    """
    items: list = []
    for document in documents:
        if document is None:  # an empty document, e.g. between two `---` markers
            continue
        items.extend(document if isinstance(document, list) else [document])
    return items


def _discover_scenarios() -> list:
    """Discover every runnable scenario: decorated test functions, plus scenario files.

    Both are needed for `list` to answer the question the user is actually asking — "what can I
    run?". Scanning only the package's own ``tests/`` meant a project that had just run
    `scrutineer init` was told it had no scenarios while holding a dozen of them.
    """
    return _discover_scenarios_with_problems()[0]


def _discover_scenarios_with_problems() -> tuple[list, list[str]]:
    """Discover runnable scenarios, plus a line describing every file that could not be read."""
    scenarios = _discover_decorated_scenarios()
    files, problems = _discover_scenario_files()
    return scenarios + files, problems


def _discover_or_report() -> tuple[list, list[str]]:
    """Discover scenarios and echo one line per unreadable file. Never exits.

    Aborting was the previous behaviour and it was worse than the bug it fixed: an unrelated
    multi-document manifest, or an editor's read-only lock file, anywhere under `scenarios/` made
    `list`, `run --all`, `run --scenario <a perfectly good one>` and `info` all exit 1. A file
    that cannot be *classified* is not evidence that anything is wrong with the files that can.
    The problems are returned so `run --all` can still refuse to look like a complete run.
    """
    scenarios, problems = _discover_scenarios_with_problems()
    for problem in problems:
        click.echo(f"[scrutineer] WARNING: {problem}", err=True)
    return scenarios, problems


def _discover_decorated_scenarios() -> list:
    """Discover test scenarios from scrutineer_test-decorated functions.

    Searches for pytest-compatible test functions with the _scrutineer_test
    attribute set by the @scrutineer_test decorator.
    """
    from scrutineer.runner import TestScenario

    scenarios = []

    # Look for test files in the standard locations
    project_root = Path(__file__).parent.parent.parent
    test_dirs = [project_root / "tests", project_root / "test"]

    for test_dir in test_dirs:
        if not test_dir.exists():
            continue
        for test_file in test_dir.rglob("test_*.py"):
            try:
                # Import the test module
                rel_path = test_file.relative_to(project_root)
                module_name = str(rel_path.with_suffix("")).replace("/", ".").replace("\\", ".")
                mod = importlib.import_module(module_name)

                # Find scrutineer_test-decorated functions
                for attr_name in dir(mod):
                    attr = getattr(mod, attr_name, None)
                    if callable(attr) and getattr(attr, "_scrutineer_test", False):
                        scenario = TestScenario(
                            id=attr_name,
                            name=attr.__name__,
                            description=attr.__doc__ or "",
                            task=getattr(attr, "_scrutineer_task", ""),
                            tags=getattr(attr, "_scrutineer_tags", []),
                            timeout_seconds=getattr(attr, "_scrutineer_timeout", 30),
                        )
                        scenarios.append(scenario)
            except (KeyboardInterrupt, SystemExit):
                raise
            except BaseException:
                # Best-effort by design, and deliberately broader than `Exception`: a module can
                # refuse to import for many reasons, one of which is pytest's `Skipped`, which
                # derives from BaseException. A user's test module that `importorskip`s a missing
                # optional dependency must not take every scenario in the project down with it.
                continue

    return scenarios


def _is_environment_dir(directory: Path, name: str) -> bool:
    """Is this an installed environment rather than somewhere a user keeps scenarios?"""
    if name.lower() in _SCENARIO_ENV_DIRS:
        return True
    try:
        return (directory / "pyvenv.cfg").is_file()
    except OSError:
        # An unreadable directory is reported by the walk's onerror; probing it must not raise,
        # or checking for an environment replaces the failure we were trying to avoid.
        return False


def _note_if_scenarios(directory: Path, problems: list[str], reason: str) -> None:
    """Record a problem if a directory we did not enter actually holds a *runnable scenario*.

    A matching file suffix is not enough. A linked directory of ordinary configs
    (`settings.json`, a workspace `package.json`) has exactly the right extension and nothing
    runnable in it; reporting that as "holds scenario files" was both false and enough to turn a
    correct tree into a failed run.
    """
    try:
        names = os.listdir(directory)
    except OSError:
        return  # an unreadable directory is reported by the walk's onerror instead

    for name in names:
        if Path(name).suffix.lower() not in _SCENARIO_FILE_SUFFIXES:
            continue
        try:
            documents = _read_scenario_documents(directory / name)
        except Exception:  # noqa: BLE001 - best-effort: this is a note, not the walk's verdict
            continue
        if any(_is_scenario_item(item) for item in _iter_scenario_items(documents)):
            problems.append(
                f"'{directory}' {reason}, and it holds at least one runnable scenario — only "
                f"{' and '.join(_SCENARIO_DIRS)} are searched"
            )
            return


def _scenario_candidates(directory: Path, problems: list[str]):
    """Yield scenario-file paths under a directory, recording what the walk refused to enter.

    ``os.walk`` rather than ``Path.rglob`` for ``onerror``: rglob swallows a permission error and
    silently drops the whole subtree, which is the same silent under-report this module exists to
    prevent. Three kinds of directory are not entered, and each is *reported* when it turns out to
    hold something runnable, because a drop you are told about is a different thing from a drop:
    environment trees, hidden trees and ``__pycache__``, and directory symlinks.

    Candidates must be real files. A dangling symlink whose name ends in ``.yaml`` — an editor's
    lock file, or a scenario whose target moved — is not an unreadable scenario, and treating it
    as one failed an entire run in which every scenario passed.
    """
    for root, dirnames, filenames in os.walk(
        directory,
        onerror=lambda exc: problems.append(
            f"'{getattr(exc, 'filename', directory)}' could not be searched: {exc.strerror}"
        ),
    ):
        root_path = Path(root)
        keep: list[str] = []

        for name in sorted(dirnames):
            child = root_path / name
            if child.is_symlink():
                _note_if_scenarios(child, problems, "is a symlink and was not followed")
            elif _is_environment_dir(child, name):
                # Reported unconditionally, not only when it holds a scenario: skipping a whole
                # environment is a decision the user should see, whatever happens to be inside it
                # (a venv under `scenarios/` discovers the packages' own 200 bundled examples).
                problems.append(
                    f"'{child}' is an installed environment and was not searched — put scenarios "
                    f"in {' or '.join(_SCENARIO_DIRS)}, not inside a virtualenv or node_modules"
                )
            elif name.lower() in _SCENARIO_IGNORED_DIRS or name.startswith("."):
                _note_if_scenarios(child, problems, "was skipped by name")
            else:
                keep.append(name)

        dirnames[:] = keep

        for filename in sorted(filenames):
            path = root_path / filename
            if path.suffix.lower() in _SCENARIO_FILE_SUFFIXES and path.is_file():
                yield path


def _discover_scenario_files() -> tuple[list, list[str]]:
    """Load scenario files from the conventional directories under the current directory.

    Returns ``(scenarios, problems)``. A file that cannot be read or classified becomes a
    *problem* rather than an exception: it is reported by the caller, and `run --all` turns a
    non-empty list into a non-zero exit so an incomplete run cannot look complete. Silently
    dropping a scenario stays forbidden — that is what ``problems`` is for.
    """
    found: list = []
    problems: list[str] = []
    seen: set[Path] = set()
    ids_seen: dict[str, str] = {}

    for directory_name in _SCENARIO_DIRS:
        directory = Path.cwd() / directory_name
        if not directory.exists():
            continue
        if not directory.is_dir():
            problems.append(f"'{directory}' exists but is not a directory, so it was not searched")
            continue

        for path in _scenario_candidates(directory, problems):
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)

            try:
                documents = _read_scenario_documents(path)
            except ScenarioLoadError as exc:
                # A missing PyYAML is an environment problem rather than this file's fault — but
                # it must not take `list` and `info` down with it, which is what re-raising did.
                problems.append(str(exc))
                continue
            except Exception as exc:
                problems.append(f"'{path}' could not be read and was skipped: {exc}")
                continue

            # Filter at the SAME granularity as the builder. Testing the file as a whole and then
            # building every item in it let a config document that merely shared a file with a
            # real scenario be built and executed as a scenario called "unnamed" — the defect
            # this gate exists to prevent, and one that multi-document YAML made easier to hit.
            items = _iter_scenario_items(documents)
            scenario_items = [item for item in items if _is_scenario_item(item)]

            strays = [item for item in items if not isinstance(item, dict)]
            if strays:
                # A scalar or bare list among scenario documents is nearly always a mistake, and
                # dropping it in silence is how a typo'd scenario body vanishes unannounced.
                problems.append(
                    f"'{path}' holds {len(strays)} item(s) that are not mappings and were "
                    f"skipped (first: {strays[0]!r})"
                )

            if not scenario_items:
                continue  # a config file, not a scenario

            # `_is_scenario_item` admits mappings only, so `_build_scenarios` cannot raise its
            # non-mapping ValueError from here — the filter is the guard, not an except clause.
            for scenario in _build_scenarios(scenario_items, str(path)):
                previous = ids_seen.get(scenario.id)
                if previous is not None:
                    # Two sources, one id: `run --scenario <id>` would silently run both.
                    problems.append(
                        f"duplicate scenario id '{scenario.id}' in '{path}' — already defined in "
                        f"'{previous}'; both will run"
                    )
                else:
                    ids_seen[scenario.id] = str(path)
                found.append(scenario)

    return found, problems


def _read_scenario_documents(path: Path) -> list:
    """Read every document in a JSON or YAML file.

    Shared by the explicit `--path` loader and by file discovery, so both report a missing
    PyYAML identically: naming the real reason and stopping, rather than returning empty and
    letting the caller blame the file's contents.

    ``safe_load_all``, not ``safe_load``: a multi-document YAML stream is valid YAML, and
    refusing one let a single unrelated manifest in the scenario directory abort every command
    that discovers scenarios.
    """
    content = path.read_text()

    if path.suffix.lower() in (".yaml", ".yml"):
        try:
            import yaml
        except ImportError as exc:
            raise ScenarioLoadError(
                f"reading '{path}' needs PyYAML, which normally arrives with "
                f"Scrutineer but is missing from this environment — run: pip install pyyaml"
            ) from exc
        return list(yaml.safe_load_all(content))

    return [json.loads(content)]


def _build_scenarios(items: list, source: str) -> list:
    """Turn loaded scenario items into TestScenario objects."""
    from scrutineer.runner import TestScenario

    scenarios = []

    for item in items:
        if not isinstance(item, dict):
            raise ValueError(
                f"{source}: each scenario must be a mapping, "
                f"got {type(item).__name__}: {item!r}"
            )
        scenario = TestScenario(
            id=item.get("id", item.get("name", "unnamed")),
            name=item.get("name", item.get("id", "unnamed")),
            description=item.get("description", ""),
            task=item.get("task", ""),
            tags=item.get("tags", []),
            timeout_seconds=item.get("timeout_seconds", 30),
            env_config=item.get("env_config", {}),
            # 'chaos' is the documented spelling; 'chaos_config' is accepted for
            # compatibility with the dataclass field name.
            chaos_config=item.get("chaos", item.get("chaos_config", {})),
            assertion_specs=item.get("assertions", []),
            allow_no_assertions=bool(item.get("allow_no_assertions", False)),
            agent_spec=item.get("agent", {}),
        )
        scenarios.append(scenario)

    return scenarios


def _load_scenario_file(path: str) -> list:
    """Load scenarios from a JSON or YAML file named explicitly by the user.

    The shape test still applies — without it, pointing `--path` at a config template *ran* it as
    a scenario called "unnamed" and reported a failure for a scenario nobody wrote — but here it
    produces a message saying what the file is missing, rather than the old
    "No scenarios found in file.", which said nothing about why.
    """
    file_path = Path(path)
    items = _iter_scenario_items(_read_scenario_documents(file_path))

    if not items:
        return []  # a genuinely empty file: nothing in it, and nothing to complain about

    scenario_items = [item for item in items if _is_scenario_item(item)]
    if not scenario_items:
        raise ScenarioLoadError(
            f"'{file_path}' does not look like a scenario file — a scenario needs an id or name "
            f"plus a task, agent, assertions, environment or chaos block, or two of those blocks "
            f"without a name"
        )

    return _build_scenarios(scenario_items, str(file_path))


def _deserialize_results_from_json(raw: list) -> list:
    """Deserialize a list of JSON dicts into ScrutineerResult objects."""
    from scrutineer.baseline import _deserialize_result

    return [_deserialize_result(item) for item in raw]


def _detect_git_info() -> tuple[str, str]:
    """Try to detect git SHA and branch from the current directory."""
    import subprocess

    sha = ""
    branch = ""

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            sha = result.stdout.strip()
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
    except Exception:
        pass

    return sha, branch


if __name__ == "__main__":
    cli()
