# Chaos Benchmark — Scrutineer's injectors vs production failure modes

> **Status: the injectors exist and are tested. The benchmark does not exist.**
>
> No production incident dataset has been collected and no distributional comparison has been
> run. An earlier version of this file printed percentages with report-like prefixes
> ("PagerDuty: 28% of incidents", "Microservices: 60% of outages cascade") and a
> "Correlation Evidence" section asserting a production distribution that was never measured.
> Those figures carried a bare company label — PagerDuty, AWS, OpenAI, "Microservices", "RAG
> systems" — but no report name, date or link; the column they sat in was eventually retitled
> "(motivation, not evidence)" while the numbers stayed. They have been **removed rather than
> restated** — a fidelity claim nobody can check is worth less than no claim at all.
>
> What remains is what can be verified from the implementation: which failure mode each injector
> models, and which parameters control it. The one column that is honest for every row is the
> last one.

## What each injector models

Each description below is taken from the injector's own signature in `src/scrutineer/chaos.py` —
`scrutineer.chaos` once installed — so you can check it by reading the code or by calling
`help()` on the class.

| Failure mode | Injector | What it models | Benchmarked against production data |
|---|---|---|---|
| Tool API timeout | `ToolFailureInjector(failure_type="timeout")` | A call that never returns; `probability`, `after_step` and `seed` control when and how often | No |
| Tool API error | `ToolFailureInjector(failure_type="error")` | A call that raises, with an optional `error_message` | No |
| Rate limiting | `ToolFailureInjector(failure_type="rate_limit")` | A rejected call the subject is expected to retry or fall back from | No |
| Malformed response | `ToolFailureInjector(failure_type="malformed")` | A response the subject cannot parse | No |
| Truncated response | `ToolFailureInjector(failure_type="partial")` | A response cut short mid-payload | No |
| LLM rate limiting | `LLMFailureInjector(failure_type="rate_limit")` | The model layer rejecting calls, independently of any tool | No |
| LLM timeout / partial / interrupted stream | `LLMFailureInjector(failure_type="timeout" / "partial_response" / "stream_interrupt")` | Model-layer failure modes a tool-level injector cannot express | No |
| Context truncation | `ContextDegradation(strategy="truncation")` | Context loss starting at `start_step`, growing at `degradation_rate`, capped by `max_truncation_pct` | No |
| Context noise | `ContextDegradation(strategy="noise")` | Perturbed context — signal degradation rather than loss | No |
| Context drift | `ContextDegradation(strategy="drift")` | Instruction drift that accumulates over the run | No |
| Cascading failure | `CascadingFailures` | Failure propagating through an explicit `dependency_graph`, bounded by `max_cascade_depth` and delayed by `propagation_delay_steps` | No |
| Spec drift under pressure | `SpecDrift` | Behavioural drift scaled by `intensity` (`subtle` / `moderate` / `aggressive`) and `probability` | No |
| Network partition | `NetworkPartition` | Partial — not binary — connectivity from a `connectivity` matrix, optionally healing after `heal_after_calls` | No |
| Clock skew | `ClockSkew` | A fixed timestamp offset (`skew_seconds`) plus progressive `drift_rate`, applied to `affected_tools` | No |
| Memory pressure | `MemoryPressure` | A token budget (`max_context_tokens`, `pressure_threshold`) with an eviction strategy, GC pauses and an `oom_probability` | No |

"Benchmarked against production data: No" is the honest entry for all of them. Their *mechanics*
are covered by the test suite — `tests/scrutineer/test_chaos_advanced.py` unit-tests
`NetworkPartition`, `ClockSkew`, `MemoryPressure` and the presets;
`tests/scrutineer/test_chaos_wrapper_contract.py` pins which injectors work through the wrapper
they hand out; and `tests/scrutineer/test_demo_scenarios.py` runs every shipped demo scenario
twice, asserting it passes when the agent handles its chaos and **fails when the chaos is left
unhandled**. Whether any of their *distributions* resembles a real incident stream has never been
measured, and this document will not claim it.

## Which injectors you can use from a scenario file

The schema recognises seven chaos types, but only four can be genuinely applied from a `.yaml`
file — `_WRAPPABLE_INJECTORS` in `src/scrutineer/scenario_schema.py` is the source of truth:

| Usable from a `.yaml` scenario | Rejected on purpose from a file | Python API only |
|---|---|---|
| `tool_failure` | `context_degradation` | `LLMFailureInjector` |
| `network_partition` | `spec_drift` | |
| `clock_skew` | `cascading_failures` | |
| `memory_pressure` | | |

The three refusals are deliberate and they fail loudly rather than being silently ignored. They
are step-driven — `ContextDegradation.on_step`, `CascadingFailures.on_failure`,
`SpecDrift.check_step` — and act on an agent's *context*, which the scripted reference agent does
not have: wiring them to it would compute a degradation curve and discard it, which is theatre
rather than a test. Use them through
`ScenarioRunner.run(scenario, agent_fn=...)` with a real agent.

## Why the numbers were removed

The previous table's figures were not merely unsourced, they were load-bearing: the Fidelity
column claimed "High — quadratic curve matches reality" and "High — matches real NTP drift
patterns", which is a claim about production that only a measurement could support. Removing the
percentage and keeping "matches reality" would have been worse than leaving both, because the
number is visibly missing while the verdict is not.

If you need failure rates that reflect *your* systems, they are configuration, not constants:
`probability`, `cascade_probability`, `degradation_rate` and `partition_probability` are all
parameters. The intended way to get a realistic mix is to measure your own incident history and
set them — not to adopt someone else's illustrative ones.

## What a real benchmark would require

Stated as a plan, not as results:

1. **Collect production evidence** — timeout rates, error codes and cascade patterns from a
   corpus of real incidents, with the source recorded per figure.
2. **Run equivalent scenarios** — the same failure modes at the measured rates.
3. **Compare distributions** — not point estimates: a Kolmogorov–Smirnov test between the
   simulated failure distribution and the observed one, reported with sample sizes.
4. **Validate cascade depth** — compare the cascade-depth distribution (simulated
   `max_cascade_depth` against observed cascade depth), again with the sample size.
5. **Publish the negative results too** — where a model does not match, that is the finding.

Until steps 1–4 have been done for a given claim, this document will not assert it.

## Using the injectors

The shipped presets are in `src/scrutineer/chaos_presets.py`: `PRODUCTION_INCIDENT`,
`TRAFFIC_SPIKE`, `COMPLETE_OUTAGE`, `DEPLOY_FRIDAY`, `MEMORY_LEAK`, `NETWORK_PARTITION` and
`TIME_TRAVEL`.

1. **Start from a preset** — `PRODUCTION_INCIDENT` or `TRAFFIC_SPIKE` are reasonable baselines.
2. **Tune to your own numbers** — replace the default rates with the ones you measured.
3. **Model your real topology** — put your actual service graph into `NetworkPartition`'s
   connectivity matrix and `CascadingFailures`' dependency graph.
4. **Record a baseline** — `scrutineer baseline record` captures behaviour under this chaos, so
   a later change can be diffed against it.
5. **Check the negative control** — every scenario should have a variant that fails when the
   chaos is unhandled. A chaos test that cannot fail verifies nothing; that property is what
   `examples/chaos_scenario_unhandled.yaml` exists to demonstrate.

## Future work

- [ ] Collect production failure distributions from real incident reports, citing each source
- [ ] Implement the K–S comparison between simulated and observed distributions
- [ ] Add more partition topologies (cross-AZ, DNS failure, BGP)
- [ ] Model specific cloud provider failure patterns (AWS, GCP, Azure)
- [ ] Add latency injection (gradual degradation, not only timeout)
