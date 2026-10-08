# Changelog

All notable changes to **Sentinel** are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[SemVer](https://semver.org/).

## [Unreleased]

### Added
- CI pipeline (pytest + ruff) for Sentinel and pattern-memory.
- LICENSE file (MIT).
- **Declarative scenario schema** (`sentinel.scenario_schema`): scenario files can now
  express `assertions:` and `chaos:` blocks, compiled into real assertions and injectors.
  Invalid specs fail loudly — unknown assertion/injector types, misspelled parameters and
  missing required parameters all raise rather than being silently ignored.
- **`ScriptedAgent`** (`sentinel.script_agent`): a deterministic reference agent so a
  scenario *file* can supply a subject without Python glue. Its `on_error` policy
  (`fail` / `continue` / `fallback`) is a usable behavioural variable. It is explicitly
  not an LLM agent — for real agents use `ScenarioRunner.run(scenario, agent_fn=...)`.
- `examples/chaos_scenario_unhandled.yaml` — negative control for
  `examples/chaos_scenario.yaml`; identical chaos and assertions, an agent with no
  fallback, expected to FAIL.

### Changed
- **Distribution renamed to `sentinel-agents`.** The PyPI name `sentinel` is owned by an
  unrelated project, so the `pip install sentinel` line shipped in earlier READMEs installed
  a different library, with no error. The import package remains `sentinel` and the CLI
  remains `sentinel`; only the distribution name changes. Not yet published to PyPI.
- **A scenario that declares no assertions now FAILS.** Previously `ScenarioRunner.run()`
  returned `passed=True` after iterating zero assertions, so every file-based scenario
  reported a green it had not earned. The run now fails with a `no_assertions_declared`
  assertion result; set `allow_no_assertions: true` to collect a trace deliberately.
- `ScenarioRunner.run()` now applies the scenario's `chaos_config` (previously ignored
  entirely by the file-based path, so declared chaos injected nothing).
- CLI `sentinel run` carries `agent:`, `assertions:`, `chaos:` and `allow_no_assertions`;
  prints failure reasons without needing `--verbose`; no longer prints the status twice;
  and reports a malformed scenario as a scenario error rather than a traceback.

### Fixed
- `_build_env` silently dropped unsupported `env_config` tool keys (including
  `side_effect`); it now rejects them with guidance pointing at the `chaos:` block.
- `_apply_chaos` silently skipped an injector whose target tool did not exist; it now
  raises, since a skipped injector fakes resilience.
- Both `examples/basic_scenario.yaml` and `examples/chaos_scenario.yaml` were reporting
  `PASS (0/0 assertions)` while verifying nothing; they now declare a subject and real
  assertions.

## [0.2.0] — 2026-08-18

### Added
- Full `__all__` exports across all modules; `py.typed` marker.
- docs/API_REFERENCE.md generated from docstrings.
- 32 edge-case tests (empty scenarios, malformed YAML, missing tools).

### Changed
- Ruff target-version corrected to `py311`; imports consolidated at top of files.
- Version bumped from `0.1.0` to `0.2.0`.

## [0.1.0] — 2026-07-08

Initial release. Six development phases complete:

- **Phase 1** — Real-agent integration (LangChain ReAct harness, integration tests).
- **Phase 2** — Packaging & distribution (hatch build, git install, GitHub repo).
- **Phase 3** — Documentation & examples (QUICKSTART, CHAOS_GUIDE, ADAPTERS_GUIDE).
- **Phase 4** — Governance model resolution (deterministic comparator default).
- **Phase 5** — Polish & edge cases.
- **Phase 6** — Advanced chaos (NetworkPartition, ClockSkew, MemoryPressure, 7 presets).

516 tests passing.