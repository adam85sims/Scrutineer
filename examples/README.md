# Examples — the Scrutineer starter kit

`scrutineer init` writes a copy of this directory into your project as
`scrutineer-examples/`. The wheel ships it at `scrutineer/examples/`, so a `pip install`
user does not need a git clone to have something to run.

## Scenarios — run these with the CLI

| File | What it shows | Expected |
|------|---------------|----------|
| `basic_scenario.yaml` | Minimal case: one scripted agent, one mocked tool, three assertions | PASS |
| `chaos_scenario.yaml` | A tool failure the agent recovers from | PASS |
| `chaos_scenario_unhandled.yaml` | Negative control — identical chaos, an agent with no fallback | **FAIL on purpose** |
| `demo-scenarios/*.yaml` | The nine scenarios the WebUI lists on first run: network partition, rate limiting, refund timeout, DB/API/UI cascade, memory pressure, context degradation, spec drift | PASS; each fails when its chaos is unhandled |

```bash
scrutineer run --path scrutineer-examples/basic_scenario.yaml
scrutineer run --path scrutineer-examples/chaos_scenario_unhandled.yaml
```

The unhandled pair is the point of the whole thing: a scenario that cannot fail verifies
nothing. `tests/scrutineer/test_demo_scenarios.py` pins that property for the demo set —
every scenario declares assertions and is falsifiable.

## Scripts

| File | What it shows |
|------|---------------|
| `langchain_quickstart.py` | A real LangChain agent under the harness: mocked tools, trace capture, assertions, then chaos injection. Needs `pip install "scrutineer-agents[langchain]"` |
| `example_audit.py` | Run a governance audit and inspect the result |
| `example_session.py` | Session state and work-queue management |
| `example_model_routing.py` | Route tasks to models by capability tier |
| `example_pattern_memory.py` | Record and retrieve corrections via `pattern-memory` |

```bash
python scrutineer-examples/langchain_quickstart.py
```

## Config templates

| File | What it configures |
|------|--------------------|
| `agent-frameworks.minimal.yaml` | Governance only; other modules use defaults |
| `agent-frameworks.full.yaml` | Every module, with fallbacks |
| `agent-frameworks.ollama.yaml`, `agent-frameworks.lmstudio.yaml` | Local-model equivalents |
| `governance/auditor.{none,ollama,vllm}.yaml` | Auditor backends. `none` is the default: deterministic comparators, no LLM |

These configure the **governance audit harness**, not agent testing. Copy one into your
project root to use it:

```bash
cp scrutineer-examples/governance/auditor.none.yaml governance/auditor.yaml
```

`scrutineer list` finds these by walking `./scenarios/` and `./scrutineer-examples/`, and counts
a file only when it is shaped like a scenario — the config templates above sit in the same tree
and are deliberately ignored.
