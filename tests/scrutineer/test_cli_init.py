"""Tests for ``scrutineer init`` and for the loader's error reporting.

Both defects were found by verifying the *published* 0.3.0 artifact instead of the checkout:

* the wheel shipped no ``examples/``, while the README's Quick Start told a pip user to run
  ``examples/basic_scenario.yaml`` — both commands exited 2. ``scrutineer init`` is the fix,
  and these tests pin that what it writes actually loads and runs.
* with PyYAML absent, the loader returned ``[]`` *after* reporting the real cause, so the CLI
  printed a second, wrong error ("No scenarios found in file.") that contradicted the first.
"""

from __future__ import annotations

import sys

import pytest
from click.testing import CliRunner

from scrutineer.cli import (
    ScenarioLoadError,
    _examples_source_dir,
    _load_scenario_file,
    cli,
)
from scrutineer.runner import ScenarioRunner

# The files the README's Quick Start tells a pip user to run.
README_SCENARIOS = (
    "basic_scenario.yaml",
    "chaos_scenario.yaml",
    "chaos_scenario_unhandled.yaml",
)


@pytest.mark.parametrize("name", README_SCENARIOS)
def test_starter_kit_contains_the_readme_scenarios(name):
    """Whatever the README points at must exist — in the checkout and in the wheel."""
    assert (_examples_source_dir() / name).is_file()


def test_init_writes_a_starter_kit_that_loads_and_runs(tmp_path):
    result = CliRunner().invoke(cli, ["init", "--dir", str(tmp_path)])
    assert result.exit_code == 0, result.output

    destination = tmp_path / "scrutineer-examples"
    scenarios = _load_scenario_file(str(destination / "basic_scenario.yaml"))
    assert scenarios[0].id == "search-basic-001"

    # Written out is not the same as runnable: run it the way the README tells the user to.
    assert ScenarioRunner().run(scenarios[0]).passed


def test_init_prints_the_commands_to_run(tmp_path):
    """A copy the user cannot find is no use; the command must say what to type next."""
    result = CliRunner().invoke(cli, ["init", "--dir", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "scrutineer run --path" in result.output
    assert "scrutineer-examples/basic_scenario.yaml" in result.output


def test_init_refuses_to_clobber_an_existing_kit(tmp_path):
    runner = CliRunner()
    assert runner.invoke(cli, ["init", "--dir", str(tmp_path)]).exit_code == 0

    marker = tmp_path / "scrutineer-examples" / "basic_scenario.yaml"
    marker.write_text("must survive\n")

    result = runner.invoke(cli, ["init", "--dir", str(tmp_path)])

    assert result.exit_code == 1
    assert "--force" in result.output
    assert marker.read_text() == "must survive\n"


def test_init_force_replaces_the_kit(tmp_path):
    runner = CliRunner()
    assert runner.invoke(cli, ["init", "--dir", str(tmp_path)]).exit_code == 0

    marker = tmp_path / "scrutineer-examples" / "basic_scenario.yaml"
    marker.write_text("replaced\n")

    result = runner.invoke(cli, ["init", "--dir", str(tmp_path), "--force"])

    assert result.exit_code == 0, result.output
    assert marker.read_text() != "replaced\n"


def test_missing_pyyaml_reports_the_real_reason_once(tmp_path, monkeypatch):
    """With PyYAML absent, say so once — do not also blame the scenario's contents."""
    scenario_file = tmp_path / "scenario.yaml"
    scenario_file.write_text("id: demo\nname: Demo\n")
    monkeypatch.setitem(sys.modules, "yaml", None)  # makes `import yaml` raise for real

    with pytest.raises(ScenarioLoadError, match="PyYAML"):
        _load_scenario_file(str(scenario_file))

    result = CliRunner().invoke(cli, ["run", "--path", str(scenario_file)])

    assert result.exit_code == 1
    assert "PyYAML" in result.output
    assert "No scenarios found" not in result.output
