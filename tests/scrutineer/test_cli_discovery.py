"""Tests for scenario-file discovery — the thing behind `scrutineer list` and `run --all`.

`_discover_scenarios()` used to walk only the package's own ``tests/``, so a project that had
just run `scrutineer init` was told "No scenarios discovered." while holding a dozen files.

The first cut of this feature then failed its own adversarial review in three ways, each pinned
below:

* it **raised** for a file it could not even classify. Because one unrelated multi-document YAML
  manifest — or an editor's read-only lock file — sat in the scenario directory, `list`,
  `run --all`, `run --scenario <a perfectly good one>` and `info` all exited 1. A file that
  cannot be classified is not evidence about the files that can: those are warnings now.
* the shape gate accepted any dict carrying a ``name``, so a docker-compose file, a
  ``package.json``, a GitHub workflow, an Ansible playbook, a Grafana dashboard and a Taskfile
  were discovered and then **executed** by `run --all` as failing scenarios.
* it read with ``yaml.safe_load``, so a multi-document stream was an error rather than two
  scenarios.
"""

from __future__ import annotations

import json
import os
import sys

import pytest
from click.testing import CliRunner

from scrutineer.cli import (
    ScenarioLoadError,
    _discover_scenario_files,
    _examples_source_dir,
    _load_scenario_file,
    cli,
)

# Shaped like a scenario, and shaped to pass: one scripted agent, one mocked tool.
PASSING_SCENARIO = """\
id: discovery-demo
name: Discovery demo
task: call the search tool
env_config:
  tools:
    search:
      response:
        results:
          - "found it"
agent:
  type: script
  steps:
    - tool: search
      args:
        query: refund policy
assertions:
  - type: tool_called
    tool: search
"""

# A governance config template: a dict, but not a scenario.
CONFIG_TEMPLATE = """\
governance:
  backend:
    type: none
"""

# Files that live in a real `scenarios/` tree beside the scenarios. Every one carries a `name`,
# an `id` or a `task`, and none of them is a scenario — six of these were once executed by
# `run --all` as failing scenarios.
INFRA_CONFIGS = {
    "docker-compose.yml": "name: myproject\nservices:\n  web:\n    image: nginx\n",
    "package.json": '{"name": "myapp", "version": "1.0.0", "dependencies": {}}\n',
    "ci-workflow.yml": "name: CI\non: [push]\njobs:\n  build:\n    runs-on: ubuntu-latest\n",
    "grafana-dashboard.json": '{"id": 7, "title": "Latency", "panels": []}\n',
    "taskfile.yml": "version: '3'\ntask: deploy\n",
    "ansible-playbook.yml": "- name: Configure web server\n  hosts: all\n  tasks: []\n",
    "fixture-array.json": '[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}]\n',
}

# Malformed: unparseable, so it can never be classified as a scenario.
BROKEN_YAML = "id: broken\ntask: [unclosed\nassertions:\n  - type: no_tool_errors\n"

# Valid YAML holding one real scenario and one item that is not a mapping at all.
MIXED_ITEMS = "id: fine\ntask: x\nassertions: []\n---\n- 42\n"

MULTI_DOC_NON_SCENARIO = """\
apiVersion: v1
kind: ConfigMap
metadata:
  name: cm
---
apiVersion: v1
kind: Service
metadata:
  name: svc
"""

MULTI_DOC_SCENARIOS = """\
id: first
task: first task
assertions: []
---
id: second
task: second task
assertions: []
"""


def _write(directory, name, content, subdir="scenarios"):
    path = directory / subdir / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def _discover():
    """Discovery returns (scenarios, problems); most tests only care about the scenarios."""
    scenarios, _ = _discover_scenario_files()
    return scenarios


def test_scenario_files_in_the_conventional_dir_are_discovered(tmp_path, monkeypatch):
    _write(tmp_path, "demo.yaml", PASSING_SCENARIO)
    monkeypatch.chdir(tmp_path)

    assert [s.id for s in _discover()] == ["discovery-demo"]


def test_starter_kit_is_discovered_after_init(tmp_path, monkeypatch):
    assert CliRunner().invoke(cli, ["init", "--dir", str(tmp_path)]).exit_code == 0
    monkeypatch.chdir(tmp_path)

    ids = {s.id for s in _discover()}

    assert "search-basic-001" in ids
    assert "chaos-search-timeout-unhandled" in ids
    # 3 top-level scenarios + 9 in demo-scenarios/, and nothing else.
    assert len(ids) == 12, sorted(ids)


def test_config_templates_are_not_mistaken_for_scenarios(tmp_path, monkeypatch):
    """The kit ships config templates beside its scenarios; neither may become an 'unnamed'."""
    _write(tmp_path, "not-a-scenario.yaml", CONFIG_TEMPLATE)
    monkeypatch.chdir(tmp_path)

    assert _discover() == []


@pytest.mark.parametrize("filename", sorted(INFRA_CONFIGS))
def test_infra_config_files_are_not_mistaken_for_scenarios(tmp_path, monkeypatch, filename):
    """A dict with a `name` is not a scenario — the gate that thought so ran six of these."""
    _write(tmp_path, filename, INFRA_CONFIGS[filename])
    monkeypatch.chdir(tmp_path)

    scenarios, problems = _discover_scenario_files()

    assert scenarios == []
    assert problems == []  # a config file is not a problem, only not a scenario


def test_a_real_scenario_beside_config_files_is_still_discovered(tmp_path, monkeypatch):
    for filename, content in INFRA_CONFIGS.items():
        _write(tmp_path, filename, content, subdir="scenarios/configs")
    _write(tmp_path, "real.yaml", PASSING_SCENARIO)
    monkeypatch.chdir(tmp_path)

    assert [s.id for s in _discover()] == ["discovery-demo"]


def test_multi_document_yaml_is_not_an_error(tmp_path, monkeypatch):
    """A k8s-style bundle is valid YAML; refusing it aborted every command that discovers."""
    _write(tmp_path, "bundle.yaml", MULTI_DOC_NON_SCENARIO)
    _write(tmp_path, "good.yaml", PASSING_SCENARIO)
    monkeypatch.chdir(tmp_path)

    scenarios, problems = _discover_scenario_files()

    assert [s.id for s in scenarios] == ["discovery-demo"]
    assert problems == []

    result = CliRunner().invoke(cli, ["list"])

    assert result.exit_code == 0, result.output
    assert "discovery-demo" in result.output


def test_multi_document_yaml_can_hold_several_scenarios(tmp_path, monkeypatch):
    _write(tmp_path, "two.yaml", MULTI_DOC_SCENARIOS)
    monkeypatch.chdir(tmp_path)

    assert [s.id for s in _discover()] == ["first", "second"]


def test_uppercase_extension_is_discovered(tmp_path, monkeypatch):
    _write(tmp_path, "demo.YAML", PASSING_SCENARIO)
    monkeypatch.chdir(tmp_path)

    assert [s.id for s in _discover()] == ["discovery-demo"]


def test_unreadable_scenario_is_a_warning_and_list_still_lists(tmp_path, monkeypatch):
    """The first cut was worse than the bug it fixed: it bricked `list` itself."""
    _write(tmp_path, "broken.yaml", BROKEN_YAML)
    _write(tmp_path, "good.yaml", PASSING_SCENARIO)
    monkeypatch.chdir(tmp_path)

    _, problems = _discover_scenario_files()
    assert len(problems) == 1 and "broken.yaml" in problems[0]

    result = CliRunner().invoke(cli, ["list"])

    assert result.exit_code == 0, result.output
    assert "discovery-demo" in result.output
    assert "WARNING" in result.output and "broken.yaml" in result.output
    assert "Traceback" not in result.output


def test_run_all_says_the_run_is_incomplete_and_exits_non_zero(tmp_path, monkeypatch):
    """A partial run must not look like a complete one — that is the whole product thesis."""
    _write(tmp_path, "broken.yaml", BROKEN_YAML)
    _write(tmp_path, "good.yaml", PASSING_SCENARIO)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["run", "--all"])

    assert "Discovery demo" in result.output, result.output
    assert result.exit_code == 1, result.output
    assert "run is incomplete" in result.output


def test_non_mapping_items_in_a_mixed_file_are_skipped_and_reported(tmp_path, monkeypatch):
    """A scalar among scenario documents is nearly always a mistake, so it is not dropped quietly.

    An earlier version of this test asserted silence, on the theory that a non-mapping item is
    simply "not a scenario". A review showed the other side of it: dropping a scalar without a word
    is how a typo'd scenario body vanishes unannounced, and `run --path` raises on the same input.
    """
    _write(tmp_path, "mixed.yaml", MIXED_ITEMS)
    monkeypatch.chdir(tmp_path)

    scenarios, problems = _discover_scenario_files()

    assert [s.id for s in scenarios] == ["fine"]
    assert len(problems) == 1 and "not mappings" in problems[0]


def test_dangling_symlink_with_a_scenario_suffix_does_not_fail_the_run(tmp_path, monkeypatch):
    """An Emacs lock file is a dangling symlink named `.#file.yaml`. It is not a scenario."""
    _write(tmp_path, "demo.yaml", PASSING_SCENARIO)
    (tmp_path / "scenarios" / ".#demo.yaml").symlink_to(tmp_path / "scenarios" / "gone.yaml")
    monkeypatch.chdir(tmp_path)

    scenarios, problems = _discover_scenario_files()

    assert [s.id for s in scenarios] == ["discovery-demo"]
    assert problems == []

    result = CliRunner().invoke(cli, ["run", "--all"])
    assert result.exit_code == 0, result.output


def test_symlinked_directory_of_mere_configs_is_not_reported(tmp_path, monkeypatch):
    """Suffix alone is not evidence: a linked dir of `settings.json` holds no scenario."""
    configs = tmp_path / "cfg"
    configs.mkdir()
    (configs / "settings.json").write_text('{"theme": "dark"}\n')

    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "demo.yaml").write_text(PASSING_SCENARIO)
    (scenarios_dir / "cfg").symlink_to(configs, target_is_directory=True)
    monkeypatch.chdir(tmp_path)

    scenarios, problems = _discover_scenario_files()

    assert [s.id for s in scenarios] == ["discovery-demo"]
    assert problems == []


def test_scenario_inside_an_installed_environment_is_reported_not_run(tmp_path, monkeypatch):
    """Walking a venv pulls a package's own bundled scenarios into the run — 200 of them."""
    _write(tmp_path, "demo.yaml", PASSING_SCENARIO)
    env = tmp_path / "scenarios" / "venv"
    env.mkdir(parents=True)
    (env / "pyvenv.cfg").write_text("home = /usr\n")
    _write(tmp_path, "bundled.yaml", PASSING_SCENARIO, subdir="scenarios/venv/lib")

    monkeypatch.chdir(tmp_path)
    scenarios, problems = _discover_scenario_files()

    assert [s.id for s in scenarios] == ["discovery-demo"]
    assert len(problems) == 1 and "installed environment" in problems[0]


def test_scenario_in_a_hidden_directory_is_reported_rather_than_dropped(tmp_path, monkeypatch):
    _write(tmp_path, "demo.yaml", PASSING_SCENARIO)
    _write(tmp_path, "old.yaml", PASSING_SCENARIO, subdir="scenarios/.archive")

    monkeypatch.chdir(tmp_path)
    scenarios, problems = _discover_scenario_files()

    assert [s.id for s in scenarios] == ["discovery-demo"]
    assert len(problems) == 1 and ".archive" in problems[0]


def test_duplicate_scenario_ids_are_reported(tmp_path, monkeypatch):
    """`run --scenario <id>` would silently run both, so ambiguity is worth a warning."""
    _write(tmp_path, "a.yaml", PASSING_SCENARIO.replace("discovery-demo", "same-id"))
    _write(tmp_path, "b.yaml", PASSING_SCENARIO.replace("discovery-demo", "same-id"))
    monkeypatch.chdir(tmp_path)

    scenarios, problems = _discover_scenario_files()

    assert [s.id for s in scenarios] == ["same-id", "same-id"]
    assert len(problems) == 1 and "duplicate scenario id 'same-id'" in problems[0]


@pytest.mark.skipif(os.geteuid() == 0, reason="root can read anything, so nothing to hide")
def test_unreadable_subdirectory_is_reported_rather_than_silently_skipped(tmp_path, monkeypatch):
    """rglob swallowed this and dropped a whole subtree — the silent under-report again."""
    locked = tmp_path / "scenarios" / "locked"
    locked.mkdir(parents=True)
    _write(tmp_path, "hidden.yaml", PASSING_SCENARIO, subdir="scenarios/locked")
    _write(tmp_path, "good.yaml", PASSING_SCENARIO)
    monkeypatch.chdir(tmp_path)

    locked.chmod(0o000)
    try:
        scenarios, problems = _discover_scenario_files()
    finally:
        locked.chmod(0o755)

    assert [s.id for s in scenarios] == ["discovery-demo"]
    assert len(problems) == 1 and "locked" in problems[0]


def test_explicit_path_to_a_real_scenario_still_loads(tmp_path):
    path = _write(tmp_path, "demo.yaml", PASSING_SCENARIO, subdir=".")

    assert [s.id for s in _load_scenario_file(str(path))] == ["discovery-demo"]


def test_explicit_path_to_a_non_scenario_says_why(tmp_path):
    """Not run as a scenario called "unnamed", and not the vague "nothing found" either."""
    config = _write(tmp_path, "config.yaml", CONFIG_TEMPLATE, subdir=".")

    with pytest.raises(ScenarioLoadError, match="does not look like a scenario"):
        _load_scenario_file(str(config))

    result = CliRunner().invoke(cli, ["run", "--path", str(config)])

    assert result.exit_code == 1
    assert "does not look like a scenario" in result.output
    assert "unnamed" not in result.output


def test_explicit_path_to_an_empty_file_finds_nothing(tmp_path):
    empty = _write(tmp_path, "empty.yaml", "", subdir=".")

    assert _load_scenario_file(str(empty)) == []

    result = CliRunner().invoke(cli, ["run", "--path", str(empty)])
    assert result.exit_code == 1
    assert "No scenarios found in file." in result.output


def test_starter_kit_scenarios_are_ignored_when_the_dirs_are_absent(tmp_path, monkeypatch):
    """Discovery reads the cwd, not the installation: a bare directory finds nothing."""
    monkeypatch.chdir(tmp_path)

    assert _discover() == []
    assert _examples_source_dir().is_dir(), "the kit should still exist for `init` to copy"


def test_run_all_with_genuinely_nothing_to_run_exits_clean(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["run", "--all"])

    assert result.exit_code == 0, result.output
    assert "No scenarios discovered." in result.output


def test_run_all_with_nothing_discoverable_but_a_problem_is_not_a_clean_exit(
    tmp_path, monkeypatch
):
    """"No scenarios discovered" + exit 0 would hide an unreadable scenario file.

    Found while re-testing the revised design: with no discoverable scenarios the command exited
    before the incompleteness check could run, so a directory holding one unreadable scenario file
    looked like a directory with nothing in it.
    """
    _write(tmp_path, "broken.yaml", BROKEN_YAML)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["run", "--all"])

    assert result.exit_code == 1, result.output
    assert "run is incomplete" in result.output


# ── Defects found by the second adversarial review of this module ──────────────────────────

# A real scenario and a governance config in the SAME file, separated by a document marker.
MIXED_DOCUMENT = PASSING_SCENARIO + "---\ngovernance:\n  backend:\n    type: none\n"

# A scenario with no id and no name — which `_build_scenarios` supports, defaulting to "unnamed".
SCENARIO_WITHOUT_A_NAME = "task: do the thing\nassertions:\n  - type: no_tool_errors\n"

# One block and no name: a Taskfile, not a scenario.
TASKFILE = "version: '3'\ntask: deploy\n"


def test_config_document_sharing_a_file_with_a_scenario_is_not_built(tmp_path, monkeypatch):
    """The gate was per-file and the builder per-item, so a config document got executed."""
    _write(tmp_path, "mix.yaml", MIXED_DOCUMENT)
    monkeypatch.chdir(tmp_path)

    scenarios, problems = _discover_scenario_files()

    assert [s.id for s in scenarios] == ["discovery-demo"]
    assert problems == []

    result = CliRunner().invoke(cli, ["run", "--all"])
    assert result.exit_code == 0, result.output
    assert "unnamed" not in result.output
    assert "1 scenario(s)" in result.output


def test_scenario_without_a_name_is_discovered_when_it_has_two_blocks(tmp_path, monkeypatch):
    """`_build_scenarios` runs an id-less scenario; discovery must not be the stricter one."""
    _write(tmp_path, "unnamed-but-real.yaml", SCENARIO_WITHOUT_A_NAME)
    monkeypatch.chdir(tmp_path)

    assert [s.id for s in _discover()] == ["unnamed"]


def test_a_bare_task_key_is_still_not_a_scenario(tmp_path, monkeypatch):
    """Taskfile-shaped: one block and no name. The false-positive fix must survive."""
    _write(tmp_path, "taskfile.yml", TASKFILE)
    monkeypatch.chdir(tmp_path)

    assert _discover() == []


def test_a_scenario_inside_a_directory_named_build_is_found(tmp_path, monkeypatch):
    """Pruning content-plausible names hid scenarios; only `__pycache__` is pruned now."""
    _write(tmp_path, "real.yaml", PASSING_SCENARIO, subdir="scenarios/build/deep")
    monkeypatch.chdir(tmp_path)

    assert [s.id for s in _discover()] == ["discovery-demo"]


def test_symlinked_scenario_directory_is_reported_not_silently_dropped(tmp_path, monkeypatch):
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    (outside / "linked.yaml").write_text(PASSING_SCENARIO)

    scenarios_dir = tmp_path / "scenarios"
    scenarios_dir.mkdir()
    (scenarios_dir / "linkdir").symlink_to(outside, target_is_directory=True)
    monkeypatch.chdir(tmp_path)

    scenarios, problems = _discover_scenario_files()

    assert scenarios == []
    assert len(problems) == 1 and "symlink" in problems[0]


def test_scenario_dir_that_is_a_file_is_reported(tmp_path, monkeypatch):
    (tmp_path / "scenarios").write_text("not a directory\n")
    monkeypatch.chdir(tmp_path)

    scenarios, problems = _discover_scenario_files()

    assert scenarios == []
    assert len(problems) == 1 and "not a directory" in problems[0]


def test_missing_pyyaml_does_not_take_down_list(tmp_path, monkeypatch):
    """An environment problem must not brick `list` — that was the second review's complaint."""
    _write(tmp_path, "demo.yaml", PASSING_SCENARIO)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(sys.modules, "yaml", None)  # makes `import yaml` raise for real

    result = CliRunner().invoke(cli, ["list"])

    assert result.exit_code == 0, result.output
    assert "PyYAML" in result.output


def test_run_all_json_output_marks_an_incomplete_run(tmp_path, monkeypatch):
    """A JSON consumer keying on total/passed must not read a partial run as complete."""
    _write(tmp_path, "broken.yaml", BROKEN_YAML)
    _write(tmp_path, "good.yaml", PASSING_SCENARIO)
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(cli, ["run", "--all", "--json-output"])

    lines = result.output.splitlines()
    start = next(i for i, line in enumerate(lines) if line.strip() == "{")
    data, _ = json.JSONDecoder().raw_decode("\n".join(lines[start:]))

    assert data["total"] == 1
    assert data["incomplete"] is True
    assert len(data["discovery_problems"]) == 1
    assert result.exit_code == 1
