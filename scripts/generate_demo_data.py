#!/usr/bin/env python3
"""generate_demo_data.py — pre-compute WebUI demo data from real scenario runs.

Unlike the previous version, this script does **not** fabricate traces. It loads
the scenarios in ``examples/demo-scenarios/`` and runs each one through the real
``scrutineer`` runner, then persists the genuine ``ScrutineerResult`` in the exact
format the WebUI reads.

For every scenario two runs are produced from the *same* chaos, differing only
in the agent's error policy:

* **resilient** — the policy declared in the YAML (chaos handled) → expected pass
* **unhandled** — ``on_error: fail`` (chaos unhandled)      → expected fail

The falsifiable difference is the point: a declared run that passes while its
unhandled twin crashes is a real regression signal, not a green tick on a
hardcoded plan.

Three baselines are built from those genuine results so the WebUI compare view
shows a real v1 → v3 improvement:

    demo-v1  chaos unhandled   (the 8 failing results)
    demo-v2  partial hardening (a real mix of pass and fail)
    demo-v3  resilient agent   (the 8 passing results)

Usage:
    python scripts/generate_demo_data.py

Run from the scrutineer project root. The script clears and regenerates
``.scrutineer/runs/`` and ``.scrutineer/baselines/`` — those directories are
generated state (gitignored) and this script owns them for the demo.
"""

from __future__ import annotations

import copy
import shutil
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Allow running from a source checkout even when the package is not installed.
_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from scrutineer.baseline import record_baseline  # noqa: E402
from scrutineer.cli import _load_scenario_file  # noqa: E402
from scrutineer.runner import ScenarioRunner, ScrutineerResult  # noqa: E402
from scrutineer.web.services.persistence import save_run  # noqa: E402

SCENARIOS_DIR = _ROOT / "examples" / "demo-scenarios"
SCRUTINEER_DIR = _ROOT / ".scrutineer"
RUNS_DIR = SCRUTINEER_DIR / "runs"
BASELINES_DIR = SCRUTINEER_DIR / "baselines"


@dataclass
class DemoRun:
    """Minimal RunState shape accepted by ``persistence.save_run``."""

    run_id: str
    scenario_id: str
    scenario_name: str
    status: str
    started_at: datetime
    completed_at: datetime
    result: ScrutineerResult


def _reset_demo_state() -> None:
    """Clear generated runs/baselines so the demo set is exact, not additive."""
    if RUNS_DIR.exists():
        shutil.rmtree(RUNS_DIR)
    if BASELINES_DIR.exists():
        shutil.rmtree(BASELINES_DIR)
    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    BASELINES_DIR.mkdir(parents=True, exist_ok=True)


def _unhandled_variant(scenario):
    """Return the same scenario with the agent's chaos left unhandled."""
    variant = copy.deepcopy(scenario)
    spec = dict(variant.agent_spec or {})
    spec["on_error"] = "fail"
    spec.pop("fallback", None)
    variant.agent_spec = spec
    return variant


def _persist(result: ScrutineerResult, started_at: datetime) -> DemoRun:
    """Persist one real result as a run file and return its DemoRun record."""
    status = "pass" if result.passed else "fail"
    run = DemoRun(
        run_id=f"{result.scenario_id}-{status}-{abs(hash(started_at)) % 10**6:06d}",
        scenario_id=result.scenario_id,
        scenario_name=result.scenario_name,
        status=status,
        started_at=started_at,
        completed_at=started_at + timedelta(milliseconds=result.duration_ms),
        result=result,
    )
    save_run(run)
    return run


def main() -> int:
    if not SCENARIOS_DIR.exists():
        print(f"error: scenario directory not found: {SCENARIOS_DIR}", file=sys.stderr)
        return 1

    paths = sorted(SCENARIOS_DIR.glob("*.yaml"))
    if not paths:
        print(f"error: no scenarios in {SCENARIOS_DIR}", file=sys.stderr)
        return 1

    runner = ScenarioRunner()
    _reset_demo_state()

    print("=" * 64)
    print("  Scrutineer Demo Data Generator (real runs, not fabricated traces)")
    print("=" * 64)
    print()

    resilient: list[ScrutineerResult] = []
    unhandled: list[ScrutineerResult] = []
    now = datetime.now(UTC)

    for i, path in enumerate(paths):
        scenario = _load_scenario_file(str(path))[0]
        nice = scenario.name or scenario.id
        print(f"  Scenario: {nice}")

        base_time = now - timedelta(minutes=(len(paths) - i) * 2)

        ok = runner.run(scenario)
        _persist(ok, base_time)
        resilient.append(ok)
        print(f"    {'PASS' if ok.passed else 'FAIL':4s}  resilient   "
              f"({len(ok.assertion_results)} assertions, {ok.duration_ms:.1f}ms)")

        bad = runner.run(_unhandled_variant(scenario))
        _persist(bad, base_time + timedelta(seconds=30))
        unhandled.append(bad)
        reason = (bad.error or "assertions failed").splitlines()[0]
        print(f"    {'PASS' if bad.passed else 'FAIL':4s}  unhandled   {reason[:56]}")
        print()

    # ── Baselines: a genuine v1 (all fail) → v3 (all pass) story ──
    # demo-v2 is a real alternating mix, not a copy of either endpoint.
    mixed = [resilient[j] if j % 2 == 0 else unhandled[j] for j in range(len(resilient))]

    baselines = [
        ("demo-v1", unhandled, ["demo", "v1"], "Chaos unhandled — agent fails on every injected fault"),
        ("demo-v2", mixed, ["demo", "v2"], "Partial hardening — real mix of passing and failing runs"),
        ("demo-v3", resilient, ["demo", "v3"], "Resilient agent — chaos handled, all scenarios pass"),
    ]

    print("  Recording baselines...")
    for label, results, tags, description in baselines:
        record_baseline(
            results,
            label=label,
            tags=tags,
            description=description,
            project_root=str(_ROOT),
        )
        passed = sum(1 for r in results if r.passed)
        print(f"    {label}: {len(results)} scenarios, {passed} pass, "
              f"{len(results) - passed} fail")

    print()
    print("=" * 64)
    print(f"  {len(resilient) + len(unhandled)} real runs  ->  {RUNS_DIR}")
    print(f"  {len(baselines)} baselines    ->  {BASELINES_DIR}")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
