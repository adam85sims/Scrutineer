# Changelog

All notable changes to **Scrutineer** are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows
[SemVer](https://semver.org/).

## [Unreleased]

## [0.3.1] — 2026-10-10

### Fixed
- **The Quick Start could not work for a `pip install` user.** The 0.3.0 wheel shipped no
  `examples/` at all, so `python examples/langchain_quickstart.py` and `scrutineer run --path
  examples/basic_scenario.yaml` — the first two commands the README gives a stranger — both
  exited 2 in an empty directory. The starter kit now ships inside the package (force-included
  as `scrutineer/examples/`) and `scrutineer init` writes it into the project as
  `scrutineer-examples/`. Verified by installing the built wheel into a clean virtualenv and
  running the README verbatim from an empty cwd.
- **A missing PyYAML reported two errors, one of them wrong.** The loader printed
  "PyYAML required for YAML files." and *then* returned an empty list, so the caller added
  "No scenarios found in file." — two errors, and the false one was the last thing the user
  read. It now raises `ScenarioLoadError`, and `run` exits 1 with the real reason only.
- **The README's OpenAI adapter snippet imported a function that does not exist**
  (`wrap_agent` → `wrap_openai_agent`), so the example could not be pasted and run.
- **`scrutineer-serve` died with a traceback on any install without the `web` extra.**
  `scrutineer/web/__init__.py` imported the FastAPI-backed app at package import, which happens
  *before* the entry point function runs — so instead of naming the missing extra, the command
  raised `ModuleNotFoundError: No module named 'fastapi'`. `create_app` now resolves lazily
  (PEP 562), and the entry point reports the missing extra and exits 1, exactly as
  `scrutineer serve` already did.
- **Two user-facing install hints named the wrong distribution** — `pip install scrutineer[web]`,
  which fetches an unrelated PyPI project, the precise trap this project's README warns about.
  Both now say `scrutineer-agents[web]`, as does `src/scrutineer/web/README.md` (which ships
  inside the wheel).
- **`run --path <config file>` executed a governance template as a scenario called "unnamed"**,
  reporting a failure for a scenario nobody wrote. The scenario-shape test now applies to
  explicitly-named paths too, so the honest answer is "No scenarios found in file."
- **`examples/e2e-scenario-saved.yaml` shipped inside the starter kit.** It is a byproduct of the
  playwright run, committed by accident in `cd25c02`, and `run --all` straight after `init`
  reported it as a failure. Removed, and gitignored so it cannot come back.
- **`run --json-output` did not produce machine-readable output, and the workflow the README
  builds on it could not work.** The flag is advertised as "Machine-readable JSON output", but
  the progress and summary lines shared stdout with the document — so
  `run --all --json-output > results.json` wrote a file that was not JSON, and the next
  documented command, `baseline record --path results.json`, died on it. Human-facing lines move
  to stderr when the flag is set, so stdout is the document. That exposed the other half:
  `baseline record` raised `KeyError: 'assertion_name'`, because the emitter writes `name`/
  `error` while the deserializer demanded `assertion_name`/`error_message`. It accepts both
  spellings now, which also stops a recorded baseline silently losing every failure reason.
- **The package README's declarative-scenario example could not run.** `chaos_config:
  max_failures: 2` is not a valid chaos block (only `budget` and `injectors` are) and
  `assertions: - assert_tool_called(search)` is not a valid assertion (they are mappings with a
  `type` key). Corrected against the shipped `examples/chaos_scenario.yaml`, along with the 14
  API names the snippets used without importing and a `.json`/`.yaml` filename mismatch in the
  run command. The example is now extracted from the README and executed as part of verification.
- **`docs/CHAOS_BENCHMARK.md` no longer presents invented figures as production evidence.** Its
  table carried percentages with report-like prefixes ("PagerDuty: 28% of incidents",
  "Microservices: 60% of outages cascade") plus fidelity verdicts such as "matches reality", and
  a "Correlation Evidence" section asserting a measured production distribution. The figures are
  **removed rather than restated** — a missing number is visible, a verdict standing next to it
  is not — and every remaining row now describes only what the implementation does, checkable by
  reading the injector signatures in `src/scrutineer/chaos.py`. Every row's fidelity column reads
  "benchmarked against production data: No". Also added a table of which injectors are usable
  from a scenario file, since four are and three are refused on purpose.

### Added
- **`scrutineer list` and `run --all` now discover scenario files**, not only
  `@scrutineer_test`-decorated functions. `<cwd>/scenarios/` and `<cwd>/scrutineer-examples/` are
  scanned, so `init` → `list` → `run --all` is a closed loop instead of "No scenarios discovered."
  over a directory holding twelve of them.
  A document counts as a scenario when it carries an id or name plus a task, agent, assertions,
  environment or chaos block — **or** two of those blocks without a name, because
  `_build_scenarios` will run an id-less scenario and discovery must not be the stricter of the
  two. The test is applied **per document, not per file**: testing the file as a whole and then
  building every document in it executed a governance config that merely shared a file with a
  real scenario, as a scenario called "unnamed". A looser gate had already been shown to
  discover — and then *execute* — a docker-compose file, a `package.json`, a GitHub workflow, an
  Ansible playbook, a Grafana dashboard and a Taskfile as six failing scenarios.
  Multi-document YAML is read as multiple scenarios rather than refused, so one unrelated manifest
  cannot upset the scan. A file that cannot be read or classified is **reported, never fatal**:
  `list` warns and still lists; `run --all` warns, runs everything it can, and exits 1 with
  "this run is incomplete". `--json-output` carries `"incomplete": true` and the list of
  `discovery_problems`, so a CI consumer reading the document cannot mistake a partial run for a
  complete one, and a directory that exists but is not a directory, or a symlinked scenario
  directory holding files, is reported rather than skipped in silence. Candidates must also be
  **real files**, so an editor's lock file — a dangling symlink named `.#file.yaml` — no longer
  fails a run in which every scenario passed; a linked directory holding nothing runnable is not
  reported merely because its files have the right suffix; a virtualenv or `node_modules` sitting
  inside a scenario directory is skipped *and named*, rather than contributing the packages' own
  bundled scenarios to the run; scenarios dropped from a hidden directory are reported; and
  duplicate scenario ids are reported with both sources, since `run --scenario <id>` would
  otherwise run both without saying so.
- 54 tests added across `tests/scrutineer/test_cli_init.py`, `test_cli_discovery.py`,
  `test_web_entrypoint.py` and `test_json_roundtrip.py`.

### Changed
- **PyYAML is a core dependency** (it was in `[governance]`). YAML is the primary user-facing
  scenario format, and the WebUI and the auditor both import it at module load — so a core
  install could not run a single shipped scenario. `[governance]` remains as a resolving alias.
  This also removes four failures from a `.[dev]`-only install: `4 failed, 561 passed, 21
  skipped` → `0 failed, 607 passed, 19 skipped`, because whole YAML-dependent modules stop
  being skipped once the dependency is present.
- **`src/scrutineer/README.md` repaired.** This file ships inside the wheel, so it is the first
  thing a user who opens the installed package reads — and its first line was
  `pip install agent-frameworks[scrutineer]`, a distribution that does not exist (404 on PyPI).
  Seven stale install lines corrected, the false "zero required dependencies" claim replaced
  with the real `click` + `pyyaml`, the CLI reference rebuilt from the actual `--help` output
  (it had been missing `init`, `trace` and `serve`), and four modules added to its architecture
  tree.
- **`--json-output --verbose` still leaked to stdout.** The verbose header lines were the only
  human-facing output that did not go through the new stderr routing, so combining the two flags
  produced JSON preceded by a human header — the same defect one combination deeper, and no test
  covered that combination until now.
- **`run --all --json-output` emitted no document at all when there was nothing to run**, so
  `> results.json` produced an empty file and the next documented command died on it. It now always
  writes a document, with `total: 0`; and `baseline record` reports an unparseable results file as
  a clear error naming the command that produces one, instead of a traceback.
- **A test module that skips itself could abort scenario discovery.**
  `_discover_decorated_scenarios` caught `Exception`, but pytest's `Skipped` derives from
  `BaseException` — so a project whose test module calls `importorskip` for a missing optional
  dependency lost *every* scenario to a `Skipped` escaping that guard. It now catches
  `BaseException`, re-raising `KeyboardInterrupt` and `SystemExit`.
- `docs/QUICKSTART.md` no longer calls the release pending, installs from PyPI rather than a
  git URL, and points at paths that exist after `scrutineer init`.
- `examples/README.md` rewritten. It documented a different project's CLI (`agent-fw-setup`),
  which would now travel inside the wheel as part of the starter kit.

### Added
- `scrutineer init` — writes the starter scenarios into `<dir>/scrutineer-examples/`, prints
  the commands to run, and refuses to overwrite an existing kit without `--force`.
- 8 tests in `tests/scrutineer/test_cli_init.py`, pinning that the starter kit ships, that what
  `init` writes loads *and runs*, that it will not clobber, and that a missing PyYAML is
  reported once and truthfully.

## [0.3.0] — 2026-10-09

### Changed
- **Renamed: Sentinel → Scrutineer.** PyPI's `sentinel` is owned by an unrelated project
  (so the old README install line fetched someone else's library), and the working name
  `overseer` turned out to collide with "Overseer AI" in this exact market, as did
  Watchkeeper, WitnessAI, Attestor, Probity and Depositions. The distribution is now
  `scrutineer-agents`; the import package and console scripts are `scrutineer` /
  `scrutineer-run` / `scrutineer-serve`.

### Added
- **Wrapper-based chaos injectors are reachable from a scenario file.** `network_partition`,
  `clock_skew` and `memory_pressure` now load, inject and are falsifiable from YAML. The
  runner substitutes each injector's `ChaosToolWrapper` into the environment (§4.10). New
  demo: `examples/demo-scenarios/network-partition-cache-fallback.yaml`.
- CI pipeline (pytest + ruff) for Scrutineer and pattern-memory.
- LICENSE file (MIT).
- **Declarative scenario schema** (`scrutineer.scenario_schema`): scenario files can now
  express `assertions:` and `chaos:` blocks, compiled into real assertions and injectors.
  Invalid specs fail loudly — unknown assertion/injector types, misspelled parameters and
  missing required parameters all raise rather than being silently ignored.
- **`ScriptedAgent`** (`scrutineer.script_agent`): a deterministic reference agent so a
  scenario *file* can supply a subject without Python glue. Its `on_error` policy
  (`fail` / `continue` / `fallback`) is a usable behavioural variable. It is explicitly
  not an LLM agent — for real agents use `ScenarioRunner.run(scenario, agent_fn=...)`.
- `examples/chaos_scenario_unhandled.yaml` — negative control for
  `examples/chaos_scenario.yaml`; identical chaos and assertions, an agent with no
  fallback, expected to FAIL.

### Changed
- **Distribution renamed to `scrutineer-agents`.** The PyPI name `scrutineer` is owned by an
  unrelated project, so the `pip install scrutineer` line shipped in earlier READMEs installed
  a different library, with no error. The import package remains `scrutineer` and the CLI
  remains `scrutineer`; only the distribution name changes. Not yet published to PyPI.
- **A scenario that declares no assertions now FAILS.** Previously `ScenarioRunner.run()`
  returned `passed=True` after iterating zero assertions, so every file-based scenario
  reported a green it had not earned. The run now fails with a `no_assertions_declared`
  assertion result; set `allow_no_assertions: true` to collect a trace deliberately.
- `ScenarioRunner.run()` now applies the scenario's `chaos_config` (previously ignored
  entirely by the file-based path, so declared chaos injected nothing).
- CLI `scrutineer run` carries `agent:`, `assertions:`, `chaos:` and `allow_no_assertions`;
  prints failure reasons without needing `--verbose`; no longer prints the status twice;
  and reports a malformed scenario as a scenario error rather than a traceback.

### Fixed
- **Three of the five chaos injectors crashed the moment they fired.**
  `NetworkPartition`, `ClockSkew` and `MemoryPressure` all hand out a `ChaosToolWrapper`, whose
  first line reads `injector.tool_name` and which later reads `injector.failure_type` — neither
  of which those classes defined, so each raised `AttributeError` inside its own wrapper on the
  first call that should have injected. They now define both, the contract is written down on
  `ChaosToolWrapper`, and `tests/scrutineer/test_chaos_wrapper_contract.py` pins it. The
  `_WRAPPABLE_INJECTORS` gate had been hiding this by refusing to load them.
- **LangChain `wrap_agent` did not intercept — it delegated to the real agent, which
  called its real tools, while recording nothing and reporting success.** It now replaces
  each of the agent's tools (`agent.tools`) with a mock-backed LangChain tool, and raises
  `AgentInterceptionError` if the tools cannot be rebound rather than failing open. Tools
  left real are reported on `AgentWrapper.unintercepted_tools`. Pass `intercept=False` for
  the old adapter-only construction (see planning/COMMERCIAL_READINESS_2026-09-13.md §4.3).
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