# Sentinel — Development Queue

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
- [x] Write integration test: run LangChain agent through Sentinel with mock environment
- [x] Inject a tool failure mid-run and verify Sentinel catches the behavioral regression
- [x] Write integration test: context degradation scenario with real LangChain agent
- [x] Create example script: `examples/langchain_quickstart.py` — runnable demo
- [x] Document integration test results in docs/INTEGRATION_TESTING.md

## Phase 2: Package & Distribution

- [x] Add MANIFEST.in or verify hatch build includes all necessary files
- [x] Create .gitignore (standard Python + sentinel-specific: reports/, .brain/, baselines/)
- [x] Verify `pip install -e .` works from clean state (no leftover deps)
- [x] Verify `pip install -e ".[all]"` installs all optional dependency groups
- [x] Add version bumping strategy (hatch version or manual)
- [x] Create GitHub repo and push initial commit (https://github.com/adam85sims/Sentinel)
- [x] Verify `pip install git+https://github.com/adam85sims/sentinel.git` works

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
- [x] Write benchmark: Sentinel chaos vs real production logs (docs/CHAOS_BENCHMARK.md)

## Phase 7: WebUI & Next-Gen Features

- [ ] Design and implement a WebUI dashboard for Sentinel (running tests, viewing trace visualization, comparing baselines)
- [ ] Add model endpoint selector in the WebUI to point test runs at different LLMs/providers (OpenAI, Anthropic, local)
- [ ] Add interactive chaos configuration builder in the WebUI
- [ ] Implement live log/span streaming in WebUI using WebSockets or Server-Sent Events (SSE)
- [ ] Implement trace snapshot comparison diffing UI (visual git diff of baseline vs current run)
- [ ] Add a `pytest` plugin for native reporting and direct execution of YAML scenarios
- [ ] Add asynchronous chaos injection support for native async agent frameworks
- [ ] Implement built-in retry assertions (e.g., `assert_retried_after_failure(tool_name, max_retries=3)`)
- [ ] Implement Prometheus metrics exporter for CI/CD run dashboards
- [ ] Guard optional deps with `pytest.importorskip` in `tests/sentinel/test_edge_cases.py`
      — the two YAML edge-case tests raise `ModuleNotFoundError: No module named 'yaml'` on a
      `.[dev]`-only install (4 failures). Same class as the e2e collection abort fixed in c98109f:
      a missing extra should skip, not fail. Not a CI blocker (CI installs `.[all,dev]`).
- [ ] Give `sentinel/adapters/openai.py` the same treatment as the LangChain adapter:
      its `wrap_openai_agent` builds adapters and `invoke()` delegates, so it is still
      fail-OPEN — the agent's real FunctionTools run while the trace stays empty and the run
      reports success. §4.3 fixed this for LangChain only (see commit 1ab62c0).

---

## Done

All 6 phases complete. **647 tests passing** (656 collected incl. the 9 browser e2e tests,
which run in their own CI job).

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

- [ ] **Product/brand name — PAUSED (2026-10-08, pending Adam).** Blocks the first PyPI
      upload, and therefore Gate 3 and the whole "release → case study → outreach" sequence.
      `pyproject.toml` currently says `sentinel-agents`, which is **PROVISIONAL**.

      Known constraints, so this doesn't restart from zero: PyPI `sentinel`, `sentinel-ai`,
      `agent-sentinel` and `sentinel-harness` are all taken; and `sentinel` collides with
      Microsoft Sentinel, SentinelOne and Whitehat Sentinel — three security vendors in this
      exact market, which is the real argument against it. A Nova-flavoured name is under
      consideration (working name *Overseer*; it is on-message for a governance instrument):
      bare `overseer` is taken on both PyPI and npm, but `overseer-agents`, `agent-overseer`,
      `nova-overseer`, `overseer-harness` and `overseer-py` are all free. Note `overseer` is
      already a generic term of art for "the agent that watches the other agents", so it is a
      role word like Sentinel — findable, but hard to own.

      **Decide before any upload.** The rename is free today and effectively permanent after
      (a rename means a new project and a dead namesake). The import package (`sentinel`) and
      the CLI (`sentinel serve`) are the user-visible surface and renaming those is a breaking
      change, so the brand should land before anyone depends on them.

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

- Repo at https://github.com/adam85sims/Sentinel
- Governance default is deterministic-only (no LLM required)
- The five shipped Phase 7 items above are marked `[ ]` here despite existing — this file
  overstates remaining work, and its `Done`/`Notes` sections understated test counts until
  2026-10-08. Keep both honest; the governance audit reads this file.
- Not production-ready: §4.4 (no real agent under test) and §4.7 (auditor not client-grade)
  are both open. Do not take a paid engagement before Gate 1 and Gate 2 pass.
