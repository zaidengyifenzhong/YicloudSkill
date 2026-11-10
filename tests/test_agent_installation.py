"""Agent detection is read-only and installs only into selected, isolated roots."""

import json

import pytest
from click.testing import CliRunner

from yicloud.agents import candidate_paths, inventory
from yicloud.cli import main
from yicloud.errors import ConfigurationError
from yicloud.skill_install import existing_paths, install, sync_existing, targets


def invoke(*args):
    return CliRunner().invoke(main, ["--json", "skill", *args])


def test_no_agents_does_not_create_directories(tmp_path):
    before = set(tmp_path.rglob("*"))
    result = invoke("install")
    assert result.exit_code == 0
    assert json.loads(result.output)["data"]["paths"] == []
    assert "No supported agents detected" in result.output
    assert set(tmp_path.rglob("*")) == before


def test_auto_installs_only_detected_agents(tmp_path):
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".gemini").mkdir()
    result = invoke("install")
    assert result.exit_code == 0
    assert set(json.loads(result.output)["data"]["paths"]) == {
        str(tmp_path / ".cursor/skills/yicloud"),
        str(tmp_path / ".gemini/skills/yicloud"),
    }
    assert not (tmp_path / "codex").exists()
    assert not (tmp_path / ".claude").exists()
    assert all(row["state"] == "matching" for row in sync_existing())


def test_all_means_all_detected_not_all_known(tmp_path):
    (tmp_path / ".qwen").mkdir()
    install("all")
    assert (tmp_path / ".qwen/skills/yicloud/SKILL.md").exists()
    assert not (tmp_path / ".cursor").exists()
    assert not (tmp_path / ".claude").exists()


def test_explicit_multiple_agents_and_aliases(tmp_path):
    result = invoke("install", "--target", "cursor", "--target", "gemini")
    assert result.exit_code == 0
    assert (tmp_path / ".cursor/skills/yicloud/SKILL.md").exists()
    assert (tmp_path / ".gemini/skills/yicloud/SKILL.md").exists()
    assert not (tmp_path / ".claude").exists()


def test_custom_agent_path_is_registered(tmp_path):
    dest = tmp_path / "a new agent/custom skills/yicloud"
    result = invoke("install", "--target", "custom", "--path", str(dest))
    assert result.exit_code == 0
    assert dest in existing_paths()
    assert sync_existing()[0]["state"] == "matching"


@pytest.mark.parametrize(
    "args",
    [
        ("--target", "auto"),
        ("--target", "all"),
        ("--target", "cursor", "--target", "claude"),
    ],
)
def test_path_requires_single_explicit_agent(tmp_path, args):
    path = tmp_path / "must-not-exist"
    result = invoke("install", *args, "--path", str(path))
    assert result.exit_code != 0
    assert not path.exists()


def test_environment_overrides(tmp_path, monkeypatch):
    claude = tmp_path / "claude-custom"
    config = tmp_path / "config-custom"
    claude.mkdir()
    (config / "opencode").mkdir(parents=True)
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(claude))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config))
    install("auto")
    assert (claude / "skills/yicloud/SKILL.md").exists()
    assert (config / "opencode/skills/yicloud/SKILL.md").exists()
    assert not (tmp_path / ".claude").exists()


def test_codex_standard_and_legacy_paths(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_HOME")
    (tmp_path / ".codex").mkdir()
    assert targets("codex") == [tmp_path / ".agents/skills/yicloud"]
    legacy = tmp_path / ".codex/skills/yicloud"
    install("codex", legacy)
    assert targets("codex") == [legacy]
    assert legacy in candidate_paths()
    assert legacy in existing_paths()


def test_shared_directories_are_deduplicated(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_HOME")
    for directory in [".codex", ".cline", ".pi/agent", ".warp"]:
        (tmp_path / directory).mkdir(parents=True)
    paths = install("auto")
    assert paths == [str(tmp_path / ".agents/skills/yicloud")]
    assert len(existing_paths()) == 1


def test_multi_agent_conflict_is_preflighted(tmp_path):
    (tmp_path / ".cursor").mkdir()
    conflict = tmp_path / ".gemini/skills/yicloud"
    conflict.mkdir(parents=True)
    (conflict / "my-notes.md").write_text("keep")
    with pytest.raises(ConfigurationError, match="conflict"):
        install("auto")
    assert not (tmp_path / ".cursor/skills").exists()
    assert (conflict / "my-notes.md").read_text() == "keep"


def test_other_agents_local_edits_protected(tmp_path):
    (tmp_path / ".cursor").mkdir()
    install("auto")
    entry = tmp_path / ".cursor/skills/yicloud/SKILL.md"
    entry.write_text("user edits")
    with pytest.raises(ConfigurationError, match="local edits"):
        sync_existing()
    assert entry.read_text() == "user edits"


def test_config_files_are_not_agent_directories(tmp_path):
    (tmp_path / ".cursor").write_text("not a directory")
    assert not next(row for row in inventory() if row["name"] == "cursor")["detected"]
    assert install("auto") == []


def test_installer_harness_overrides_all_agent_environment_roots(tmp_path):
    from tools.installer_test_env import isolated_agent_env

    names = (
        "HOME",
        "USERPROFILE",
        "CODEX_HOME",
        "XDG_CONFIG_HOME",
        "CLAUDE_CONFIG_DIR",
        "HERMES_HOME",
        "VIBE_HOME",
        "APPDATA",
        "LOCALAPPDATA",
        "FLATPAK_XDG_CONFIG_HOME",
    )
    inherited = {name: "/private-user-agent" for name in names}
    inherited.update(isolated_agent_env(tmp_path))
    assert all(value.startswith(str(tmp_path)) for value in inherited.values())
