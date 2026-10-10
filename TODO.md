# Scrutineer — Development Queue

> Phase 7 is currently pending.

## Rules

1. **Pick the first `[ ]` item** under "Pending" — do it, mark `[x]`, move to "Done"
2. **New items must be added to the TODO when discovered** — only add tasks you discovered from doing other tasks
3. **Exit ONLY when ANY of these is true:**
   - Queue is empty (all items done or blocked)
   - Audit shows CRITICAL — fix first, then re-audit, then stop
   - Blocker hit (needs user input) — mark blocked with explanation, write diary, stop
   - 2 phases completed this session (excellent work — finalize and stop)
   - Cannot continue quality work (repeated failures, unavailable resources)
4. **After completing each item, IMMEDIATELY move to the next** — do not stop, summarize, or ask what to do next
5. **New items go at the END of Pending** — unless you can argue they're higher priority
6. **Never mark something done without doing it** — the governance audit checks
7. **When the queue is near empty, self-seed** — find concrete issues in the codebase and add them

---

## Phase 1: Proof of Value (Real Agent Integration)

- [x] Install langchain-core and create a minimal LangChain agent (ReAct pattern, 2 tools)
- [x] Write integration test: run LangChain agent through Scrutineer with mock environment
- [x] Inject a tool failure mid-run and verify Scrutineer catches the behavioral regression
- [x] Write integration test: context degradation scenario with real LangChain agent
- [x] Create example script: `examples/langchain_quickstart.py` — runnable demo
- [x] Document integration test results in docs/INTEGRATION_TESTING.md

## Phase 2: Package & Distribution

- [x] Add MANIFEST.in or verify hatch build includes all necessary files
- [x] Create .gitignore (standard Python + scrutineer-specific: reports/, .brain/, baselines/)
- [x] Verify `pip install -e .` works from clean state (no leftover deps)
- [x] Verify `pip install -e ".[all]"` installs all optional dependency groups
- [x] Add version bumping strategy (hatch version or manual)
- [x] Create GitHub repo and push initial commit (https://github.com/adam85sims/Scrutineer)
- [x] Verify `pip install git+https://github.com/adam85sims/scrutineer.git` works

## Phase 3: Documentation & Examples

- [x] Create docs/QUICKSTART.md — 5-minute guide from install to first test
- [x] Create docs/CHAOS_GUIDE.md — deep dive on chaos injection patterns
- [x] Create docs/ADAPTERS_GUIDE.md — how to write custom adapters
- [x] Create examples/basic_scenario.yaml — minimal YAML scenario
- [x] Create examples/chaos_scenario.yaml — chaos injection demo
- [x] Create examples/langchain_quickstart.py — runnable demo (created in Phase 1)
- [x] Update README.md with badges (CI, coverage, version)

## Phase 4: Governance Model Resolution

- [x] Document governance model options in docs/GOVERNANCE_DECISION.md
- [x] Option C: Pure deterministic comparator (selected as default)
- [x] Updated auditor.yaml to default to backend.type: "none"
- [x] Fixed auditor.py and extract.py for deterministic-only mode
- [x] Governance audit passes with deterministic comparator

## Phase 5: Polish & Edge Cases

- [x] Resolve tool count discrepancy (docs updated)
- [x] Add `__all__` exports to all modules
- [x] Create docs/API_REFERENCE.md from docstrings
- [x] Add edge case tests: empty scenarios, malformed YAML, missing tools

## Phase 6: Advanced Chaos (Differentiator Expansion)

- [x] Research additional production failure modes (network partitions, clock skew, memory pressure)
- [x] Implement NetworkPartition chaos injector
- [x] Implement ClockSkew chaos injector
- [x] Implement MemoryPressure chaos injector
- [x] Add chaos scenario presets (production incident, deploy Friday, traffic spike, etc.)
- [x] Write benchmark: Scrutineer chaos vs real production logs (docs/CHAOS_BENCHMARK.md)

## Phase 7: WebUI & Next-Gen Features

- [ ] Design and implement a WebUI dashboard for Scrutineer (running tests, viewing trace visualization, comparing baselines)
- [ ] Add model endpoint selector in the WebUI to point test runs at different LLMs/providers (OpenAI, Anthropic, local)
- [ ] Add interactive chaos configuration builder in the WebUI
- [ ] Implement live log/span streaming in WebUI using WebSockets or Server-Sent Events (SSE)
- [ ] Implement trace snapshot comparison diffing UI (visual git diff of baseline vs current run)
- [ ] Add a `pytest` plugin for native reporting and direct execution of YAML scenarios
- [ ] Add asynchronous chaos injection support for native async agent frameworks
- [ ] Implement built-in retry assertions (e.g., `assert_retried_after_failure(tool_name, max_retries=3)`)
- [ ] Implement Prometheus metrics exporter for CI/CD run dashboards
- [x] Guard optional deps with `pytest.importorskip` in `tests/scrutineer/test_edge_cases.py`
      — the two YAML edge-case tests raise `ModuleNotFoundError: No module named 'yaml'` on a
      `.[dev]`-only install (4 failures). Same class as the e2e collection abort fixed in c98109f:
      a missing extra should skip, not fail. Not a CI blocker (CI installs `.[all,dev]`).
      **RESOLVED 2026-10-10, by a different route:** the failures are gone because PyYAML is a
      core dependency now. Reproduced first, honestly: `.[dev]`-only was `4 failed, 561 passed,
      21 skipped`, and the 4 were not all where this item said — 2 in `test_edge_cases.py`
      (`import yaml` inside the test bodies) and 2 in `tests/test_governance.py`
      (`auditor.yaml` would not load: "PyYAML not installed; cannot load auditor.yaml"). After
      the dependency move: `0 failed, 607 passed, 19 skipped`, and the extra tests appear
      because whole YAML-dependent modules stop being skipped. No `importorskip` was needed for
      yaml; the general rule stays in AGENTS.md for the extras that really are optional
      (`langchain`, `crewai`, `openai`, `fastapi`).
- [ ] Give `scrutineer/adapters/openai.py` the same treatment as the LangChain adapter:
      its `wrap_openai_agent` builds adapters and `invoke()` delegates, so it is still
      fail-OPEN — the agent's real FunctionTools run while the trace stays empty and the run
      reports success. §4.3 fixed this for LangChain only (see commit 1ab62c0).

---

## Done

All 6 phases complete. **701 tests passing** (710 collected incl. the 9 browser e2e tests,
which run in their own CI job).

- [x] **0.3.1 published to PyPI (2026-10-10, evening)** — `scrutineer-agents 0.3.1`, wheel +
  sdist, from commit `cbdcba8`. Verified by installing *from PyPI* into a fresh venv and running
  the README verbatim from an empty directory: `--version` reports 0.3.1, `init` exits 0,
  `run basic` PASS, `run --path chaos_scenario_unhandled.yaml` FAIL (by design),
  `run --all` = 12 scenarios / 11 passed / 1 failed (the shipped negative control),
  `list` finds 12 with no warnings, and PyYAML arrives as a core dependency.
  - **Open:** the upload used the legacy `~/.pypirc` token, **not** the OIDC trusted-publisher
    path the `publish.yml` workflow is built around, because `gh` is not authenticated on this
    machine and the workflow only triggers on a published GitHub Release. No GitHub Release or
    `v0.3.1` tag exists. Cutting one now would re-run the workflow and fail with "File already
    exists" (the workflow's own comment anticipates this as a wiring test). **Rotate the PyPI
    token** — it appeared in a chat log earlier.
  - **Open:** `git remote` still points at `Sentinel.git`, which redirects; every push prints a
    "repository moved" notice. One `git remote set-url` fixes it, left to Adam.

- [x] **0.3.1 first-run pass (2026-10-10, afternoon)** — the same "it lies" class, hunted further
      down the same path. Verified from wheels built from this tree, installed into clean venvs:
      - `src/scrutineer/README.md` (ships inside the wheel) opened with
        `pip install agent-frameworks[scrutineer]` — a distribution that 404s on PyPI. Seven
        install lines corrected, the false "zero required dependencies" claim replaced with the
        truth (`click` + `pyyaml`), and the CLI reference rebuilt from the real `--help` output;
        it had been missing `init`, `trace` and `serve`.
      - `scrutineer-serve` raised `ModuleNotFoundError: No module named 'fastapi'` on any install
        without the `web` extra, because `scrutineer/web/__init__.py` imported the FastAPI-backed
        app at package import — before the entry point could report anything. `create_app` is now
        lazy; the command names the missing extra and exits 1.
      - Two install hints told users to run `pip install scrutineer[web]` — the *other* PyPI
        project, the exact trap the README warns about. Corrected, including the copy that ships
        in the wheel.
      - `scrutineer list` could not see scenario files, so `init` then `list` answered "No
        scenarios discovered." over twelve of them. Discovery now reads `./scenarios/` and
        `./scrutineer-examples/`, distinguishing a scenario from the config templates that share
        those trees; `init → list → run --all` is a closed loop (12 found, 11 pass, 1 fails by
        design).
      - `run --path <config file>` executed a governance template as a scenario called "unnamed".
      - `examples/e2e-scenario-saved.yaml`, a committed playwright byproduct, shipped in the kit
        and made `run --all` report a failure out of the box. Removed + gitignored.
      Evidence: 665 tests pass serially and under `-n auto -p randomly`; ruff clean;
      `twine check` PASSED; both entry points exercised on lean and full installs. Still
      unpublished — `pyproject.toml` reads 0.3.0.
- [x] The rename was done in the repo README's OpenAI snippet twice over: `wrap_agent` does not
      exist in `scrutineer/adapters/openai.py` (it is `wrap_openai_agent`), so that snippet
      could not be pasted and run. All four adapter snippets now verified to import.
- [x] `docs/QUICKSTART.md` no longer says "(release pending)", no longer installs from a git
      URL while 0.3.0 sits on PyPI, and no longer points at `scenarios/basic.yaml`, a path no
      user has.
- [x] `examples/README.md` rewritten — it documented a different project's CLI
      (`agent-fw-setup init`), and would now ship inside the wheel as part of the starter kit.

- [x] **Renamed: Sentinel → Scrutineer (2026-10-09)** — 1603 substitutions across 117 files,
      6 path moves; 647 tests still pass, ruff clean, wheel rebuilt as `scrutineer_agents-0.3.0`.
      Two defects found *by* the rename: `click.version_option(package_name=…)` must name the
      DISTRIBUTION (`scrutineer-agents`) or `--version` raises at runtime while the suite stays
      green; and a rename leaves orphaned console scripts + `*-dist-info` in `.venv`.

- [x] Phase 1: LangChain integration tests (16 tests)
- [x] Phase 2: Package & distribution (build, install, version bump)
- [x] Phase 3: Documentation & examples (3 guides, 2 scenarios, README)
- [x] Phase 4: Governance resolution (deterministic auditor)
- [x] Phase 5: Polish (__all__ exports, API ref, 32 edge case tests)
- [x] Phase 6: Advanced chaos (3 new injectors, 7 presets, benchmark doc)
- [x] CI green on `main` (2026-10-08) — `test` (3.11/3.12/3.13) + `e2e (browser)` + `lint`
- [x] LangChain `wrap_agent` genuinely intercepts, and fails closed (§4.3)
- [x] Wrapper-based chaos injectors reachable from a scenario file, and working at all (§4.10)

## Blocked

*(none)*

- [x] **GitHub repo is still named `Sentinel`** — pending Adam (browser, ~30s). **CLOSED
      2026-10-10, verified:** the rename happened on 2026-10-09. `api.github.com/repos/
      adam85sims/Scrutineer` → 200 (`full_name: adam85sims/Scrutineer`, `default_branch: main`,
      last push 2026-10-09T02:18Z); `/Sentinel` → 301. The 0.3.0 project URLs resolve. The item
      above is kept only so the record shows the blocker really did clear before the publish.
      Cosmetic leftover: the local remote still reads `.../Sentinel.git` (it works, via the
      redirect) — update with
      `git remote set-url origin https://github.com/adam85sims/Scrutineer.git`.

## Name decision (2026-10-09) — DECIDED: Scrutineer

**Brand:** Scrutineer · **distribution:** `scrutineer-agents` · **import package + CLI:**
`scrutineer` / `scrutineer-run` / `scrutineer-serve`.

A scrutineer is the independent official who inspects a thing against the rulebook and
certifies it — which is the job description of the audit, and explicitly *independent of
the thing being inspected*, which is the whole pitch.

Verified 2026-10-09 (PyPI + npm + DNS) so this never has to restart from zero:

| Candidate | Verdict |
|---|---|
| `sentinel` | PyPI-owned by an unrelated project; collides with Microsoft Sentinel, SentinelOne and Whitehat Sentinel in this exact market. |
| `overseer` | **Overseer AI** (overseerai.app) is a live AI-safety/compliance API; PyPI `overseer-ai` is an agent-reliability package. Direct collision. |
| `watchkeeper` | Bit Zesty's Watchkeeper is an AI agent that reviews evidence for ISO 27001 audits — the same offer. |
| `witness` | WitnessAI — "unified AI security and governance platform". |
| `attestor`, `probity`, `deposition`, `groundtruth`, `warden`, `tribunal`, `arbiter`, `verifier`, `custodian`, `assayer`, `plumbline`, `litmus`, `signet`, `hallmark`, `rulebook`, `crucible`, `sextant`, `reagent`, `lodestone` | All PyPI-claimed, most by AI-eval / agent-observability tooling. |
| `scrutineer` | PyPI-owned (`scrutineer 1.6.4`, "agentic code review toolkit for Claude Code") — different function, adjacent niche. `scrutineer-agents` free on PyPI **and** npm; `scrutineer-agents.com/.dev/.io` free. **CHOSEN.** |

The descriptive lane in this market is crowded — further support for selling the report
(readiness §5) rather than competing on the tool's name.

Rename cost, for the record: 1603 substitutions across 117 files, 6 path moves.

## Found during the 0.3.0 publish verification (2026-10-09)

Verified against the PUBLISHED artifact — clean venvs, installed from PyPI, run from an
empty cwd — not against the repo checkout:

- [x] 🔴 **The README's Quick Start cannot work from the published wheel.** The wheel ships
      `scrutineer/`, `governance/`, `common/` only — no `examples/` — yet Quick Start tells
      the reader to run `python examples/langchain_quickstart.py` and
      `scrutineer run --path examples/basic_scenario.yaml`. The sdist *does* carry
      `examples/` (26 files), so only source installs work. This is the first command a
      stranger types after `pip install scrutineer-agents` — §4.1's failure class again.
      **FIXED 2026-10-10:** `examples/` is force-included into the wheel as
      `scrutineer/examples/` (26 files at the time — 25 once the committed e2e fixture below was
      removed) and `scrutineer init`
      writes it into the project as `scrutineer-examples/`. Verified by installing the built
      wheel into a clean venv and running the new Quick Start verbatim from an empty cwd:
      `init` → 0, `basic_scenario.yaml` → PASS 0, `chaos_scenario_unhandled.yaml` → FAIL 1.
- [x] 🟠 **YAML scenarios need `pyyaml`, which is in the `[governance]` extra, not core.**
      So the advertised zero-dependency install cannot run any shipped scenario. Verified:
      core venv prints "PyYAML required for YAML files." and then, misleadingly,
      "No scenarios found in file." **FIXED 2026-10-10:** `pyyaml>=6.0` is now a core
      dependency (`[governance]` stays as a resolving alias), and the loader raises
      `ScenarioLoadError` so the CLI prints the true reason once and exits 1 — the second,
      false message is gone.
- [x] Everything else verified good on the published artifact: core install pulls exactly
      `click` + the package; wheel carries `scrutineer/`+`governance/`+`common/`;
      `scrutineer --version` → 0.3.0; `scrutineer serve` from an EMPTY cwd → `/api/health`
      200 (B2 holds), `/api/baselines` 200, `/api/scenarios` 200; `twine check` PASSED on
      wheel and sdist; CI green on the renamed tree (all five jobs, `dc0e692`); published
      project URLs resolve 200.

## Docs truth pass (2026-10-09)

- [x] **The uncited "88% of AI agents fail in production" headline is gone.** Replaced in
      README, `docs/CHAOS_GUIDE.md` and `docs/PROJECT_REVIEW.md` with two verified primaries:
      RAND RR-A2680-1 (2024) for ">80% of AI projects fail, twice the rate of non-AI IT
      projects", and the PwC 2026 AI Performance Study (1,217 executives; 74% of value to
      20% of organisations) for the pilot-to-value gap. No primary source for 88% exists — it
      is 100% minus the 11-14% of pilots reaching production in vendor surveys, and the copies
      that repeat it attribute it inconsistently (PwC / Composio / Bonjoy / RAND); one states
      88% in the headline and computes 86% in the body. The failure-mode breakdown was dropped
      entirely: unsourced, and it sums to 80%.
- [x] 🔴 **`docs/CHAOS_BENCHMARK.md` presents invented numbers as real-world sources.** Its
      table asserted "PagerDuty: 28% of incidents", "RAG systems: 15-30% irrelevant
      retrieval", "Microservices: 60% of outages cascade" and a dozen more with no citation,
      date or report name, and its "Correlation Evidence" section claimed a production
      distribution that was never measured — the doc's own method section lists collecting
      production logs as a future step. These are the figures the README breakdown was
      relabelled from. Column retitled and flagged 2026-10-09.
      **FIXED 2026-10-10:** rewritten. Every unsourced figure is **removed rather than
      restated** — removing the number while keeping the verdict beside it ("High — matches
      reality") would have been the worse half-fix, since the missing number is visible and the
      verdict is not. Every remaining row describes only what the implementation does, sourced
      from each injector's signature in `scrutineer/chaos.py`, and the fidelity column now reads
      "benchmarked against production data: No" for all fifteen rows. Added a table of which
      injectors are usable from a scenario file (four; three are refused on purpose and
      `LLMFailureInjector` is Python-only), checked against `_WRAPPABLE_INJECTORS`.

## Open Questions

- 🔴 **`baseline record` writes into the Python environment, not the user's project.**
  `get_baseline_dir()` derives the project root from `Path(__file__).parent.parent.parent`: the
  repo root for a source checkout, but `lib/python3.11/` for an installed wheel. Verified on a
  clean venv install of the built wheel — from a scratch project directory,
  `scrutineer baseline record mybaseline --path results.json` created
  `<venv>/lib/python3.11/.scrutineer/baselines/mybaseline`, i.e. *inside the venv*, and nothing
  in the user's own directory. So every pip user's baselines live in a directory a reinstall
  destroys and that every project sharing that venv also writes to; `diff` and `report` read
  back from the same place, so it looks like it works. Recommended fix: default to
  `Path.cwd()`, or search upward from cwd for `.git`/`pyproject.toml`, with an explicit
  override. Deliberately not changed here — where a tool stores a user's data is a product
  decision, and `tests/conftest.py`'s `tmp_baseline_dir` insulates the suite either way.
- **`AGENTS.md` still says YAML loading needs `.[governance]`** ("CLI and scenarios"), which now
  contradicts `pyproject.toml`. The correcting edit was refused by the protected-agent-file
  guard and has deliberately not been retried. The same file's *Working notes* did receive the
  2026-10-10 lessons — check whether that landed, and whether it should stay.
- **The WebUI writes scenarios it saves into `examples/`.** `scrutineer-serve --scenario-dir`
  defaults to `examples`, so a save from the browser edits the *repository's* example tree — that
  is how `examples/e2e-scenario-saved.yaml` got committed in the first place. It should default
  to a user-owned directory (`.scrutineer/scenarios/`, say). Not fixed: it changes the WebUI's
  storage contract and the e2e tests assert against it.
- **The README presents the OpenAI adapter as a working drop-in** (`wrap_openai_agent`) while
  the adapter is still fail-open (see the pending item above). Fix the adapter, or say plainly
  in the README that it is adapter-construction only today. Deliberately left to Adam: that is
  product messaging, not a typo.

- Phase 7's queue is ~half stale: of its 11 pending items, **5 are already built** (WebUI
  dashboard, model-endpoint selector, chaos config builder, SSE streaming, trace/baseline
  diff UI). Only four features are genuinely unstarted: pytest plugin, async chaos, retry
  assertions, Prometheus exporter. Worth re-cutting the queue by gate (Gate 0 "not lying" →
  Gate 4 "sellable") instead of by phase, so correctness defects stop queueing behind
  telemetry.
- Pricing signed off line by line, and the pilot-discount rule decided (readiness §7 item 10).
- `pattern-memory/` (v0.13.0) has never had a release/CI assessment, yet the offer plan treats
  it as a second instrument of the service (readiness §4.9).
- Docker for the WebUI: secondary distribution channel, not launch-blocking.
- The governance diary is stale (claims 521 tests; the real count is 656). That is why the
  audit FAILs on its own repo and the on-file PASS case study no longer reproduces. Refresh
  the diary and regenerate the case study before anything is published.

## Notes

- Repo at https://github.com/adam85sims/Scrutineer
- Governance default is deterministic-only (no LLM required)
- **Unreleased (targeting 0.3.1):** `pyyaml` is a core dependency; `scrutineer init` writes the
  starter kit; `examples/` is force-included into the wheel. On a fresh build, expect 26
  `scrutineer/examples/` files in the wheel and `Requires-Dist: pyyaml>=6.0` with no extra.
- **Re-check this after every build:** `unzip -l dist/*.whl` and then run the README from an
  empty cwd in a clean venv. The suite being green does not mean the wheel is complete — 0.3.0
  proved that.
- The five shipped Phase 7 items above are marked `[ ]` here despite existing — this file
  overstates remaining work, and its `Done`/`Notes` sections understated test counts until
  2026-10-08. Keep both honest; the governance audit reads this file.
- PyPI: `scrutineer-agents 0.3.0` built; `twine check` PASSED on wheel + sdist. Upload uses
  `~/.pypirc` (token stored 2026-10-09 — **rotate it after the first upload**: it was pasted
  into a chat log). Import package `scrutineer` shares its name with PyPI's unrelated
  `scrutineer 1.6.4`, so the two cannot be co-installed (accepted pattern: pillow→PIL).
- **Published 2026-10-09:** `scrutineer-agents 0.3.0` on PyPI
  (https://pypi.org/project/scrutineer-agents/0.3.0/); GitHub repo renamed to
  `adam85sims/Scrutineer` (old URL 301-redirects). Installed from PyPI and smoke-tested.
- README badge corrected 520 → 647.
- Not production-ready: §4.4 (no real agent under test) and §4.7 (auditor not client-grade)
  are both open. Do not take a paid engagement before Gate 1 and Gate 2 pass.
