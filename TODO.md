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
- [ ] Guard optional deps with `pytest.importorskip` in `tests/scrutineer/test_edge_cases.py`
      — the two YAML edge-case tests raise `ModuleNotFoundError: No module named 'yaml'` on a
      `.[dev]`-only install (4 failures). Same class as the e2e collection abort fixed in c98109f:
      a missing extra should skip, not fail. Not a CI blocker (CI installs `.[all,dev]`).
- [ ] Give `scrutineer/adapters/openai.py` the same treatment as the LangChain adapter:
      its `wrap_openai_agent` builds adapters and `invoke()` delegates, so it is still
      fail-OPEN — the agent's real FunctionTools run while the trace stays empty and the run
      reports success. §4.3 fixed this for LangChain only (see commit 1ab62c0).

---

## Done

All 6 phases complete. **647 tests passing** (656 collected incl. the 9 browser e2e tests,
which run in their own CI job).

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

- [ ] **GitHub repo is still named `Sentinel`** — pending Adam (browser, ~30s).
      `pyproject.toml` and `README.md` project URLs now point at
      `github.com/adam85sims/scrutineer`, which 404s until the repo is renamed
      (Settings → Repository name). GitHub redirects the old URL permanently afterwards, so
      the local remote keeps working either way. This is the last blocker on a clean 0.3.0
      project page: **PyPI release metadata cannot be edited after upload**, so either the
      rename lands before the publish, or 0.3.0 ships a dead project link.

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

- [ ] 🔴 **The README's Quick Start cannot work from the published wheel.** The wheel ships
      `scrutineer/`, `governance/`, `common/` only — no `examples/` — yet Quick Start tells
      the reader to run `python examples/langchain_quickstart.py` and
      `scrutineer run --path examples/basic_scenario.yaml`. The sdist *does* carry
      `examples/` (26 files), so only source installs work. This is the first command a
      stranger types after `pip install scrutineer-agents` — §4.1's failure class again.
      Fix: ship starter scenarios inside the package plus a `scrutineer init`/`demo` command
      that writes one, or point Quick Start at the repo. Target 0.3.1.
- [ ] 🟠 **YAML scenarios need `pyyaml`, which is in the `[governance]` extra, not core.**
      So the advertised zero-dependency install cannot run any shipped scenario. Verified:
      core venv prints "PyYAML required for YAML files." and then, misleadingly,
      "No scenarios found in file." Fix: make pyyaml a core dependency (YAML is the primary
      user-facing path) or document `scrutineer-agents[governance]`, and make the loader exit
      on the real reason rather than printing a second, wrong one. Target 0.3.1.
- [x] Everything else verified good on the published artifact: core install pulls exactly
      `click` + the package; wheel carries `scrutineer/`+`governance/`+`common/`;
      `scrutineer --version` → 0.3.0; `scrutineer serve` from an EMPTY cwd → `/api/health`
      200 (B2 holds), `/api/baselines` 200, `/api/scenarios` 200; `twine check` PASSED on
      wheel and sdist; CI green on the renamed tree (all five jobs, `dc0e692`); published
      project URLs resolve 200.

## Open Questions

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
- README badge corrected 520 → 647. The uncited "88% of AI agents fail in production" claim
  still stands in README/docs/CHAOS_GUIDE/PROJECT_REVIEW — deliberately left for Adam to
  cite or cut, because it is a marketing decision, not a typo.
- Not production-ready: §4.4 (no real agent under test) and §4.7 (auditor not client-grade)
  are both open. Do not take a paid engagement before Gate 1 and Gate 2 pass.
