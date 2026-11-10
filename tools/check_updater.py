"""Test real uv/pipx/venv updates between same-version local Git commits.

Only discovery/provenance is controlled to stand in for the official GitHub
repository. Installers, console entry points, commit verification and Skills
are real; no cloud credentials or external network are needed after download.
"""

import argparse
import email
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import venv
import zipfile
from pathlib import Path

from installer_test_env import isolated_agent_env, isolated_path

REPOSITORY = "https://github.com/zaidengyifenzhong/YicloudSkill.git"


def source_repository(wheel, directory):
    repo = directory / "source"
    repo.mkdir()
    with zipfile.ZipFile(wheel) as archive:
        metadata = email.message_from_bytes(
            archive.read(next(n for n in archive.namelist() if n.endswith("/METADATA")))
        )
        version = metadata["Version"]
        dependencies = [d for d in metadata.get_all("Requires-Dist", []) if "extra ==" not in d]
        for name in archive.namelist():
            if name.startswith("yicloud/"):
                assert ".." not in Path(name).parts
                path = repo / "src" / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(name))
    (repo / "pyproject.toml").write_text(
        '[build-system]\nrequires = ["setuptools>=77"]\nbuild-backend = "setuptools.build_meta"\n'
        '[project]\nname = "yicloud-skill"\nversion = ' + json.dumps(version) + "\n"
        'requires-python = ">=3.10"\ndependencies = ' + json.dumps(dependencies) + "\n"
        '[project.scripts]\nyicloud = "yicloud.cli:main"\n'
        '[tool.setuptools.packages.find]\nwhere = ["src"]\n'
        '[tool.setuptools.package-data]\nyicloud = ["data/*.json", "skill/**/*.md", "skill/**/*.yaml", "skill/*.md", "skill/scripts/*.py"]\n',
        encoding="utf-8",
    )
    entry = repo / "src/yicloud/skill/SKILL.md"
    original = entry.read_bytes()
    entry.write_bytes(original + b"\nInitial fixture commit.\n")

    def git(*args):
        return subprocess.run(
            [
                "git",
                "-c",
                "core.hooksPath=.git/no-hooks",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "user.name=YicloudFixture",
                "-c",
                "user.email=fixture@example.invalid",
                *args,
            ],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init", "--initial-branch=main")
    git("add", ".")
    git("commit", "-m", "Initial fixture")
    before = git("rev-parse", "HEAD")
    entry.write_bytes(original)
    git("add", ".")
    git("commit", "-m", "Same version, new Skill commit")
    after = git("rev-parse", "HEAD")
    return repo, version, before, after


def verify(wheel, wheelhouse, manager):
    with tempfile.TemporaryDirectory(prefix=f"yicloud-update-{manager}-") as temporary:
        root = Path(temporary)
        repo, version, before, after = source_repository(wheel, root)
        env = dict(os.environ)
        env.pop("PYTHONPATH", None)
        for key in list(env):
            if key.startswith("YICLOUD_") or key in {
                "CLAUDE_CONFIG_DIR",
                "HERMES_HOME",
                "VIBE_HOME",
                "FLATPAK_XDG_CONFIG_HOME",
            }:
                env.pop(key)
        env.update(
            PATH=isolated_path(root),
            HOME=str(root),
            USERPROFILE=str(root),
            CODEX_HOME=str(root / "codex"),
            XDG_CONFIG_HOME=str(root / ".config"),
            YICLOUD_CONFIG=str(root / "config.json"),
            UV_TOOL_DIR=str(root / "tools"),
            UV_TOOL_BIN_DIR=str(root / "bin"),
            UV_CACHE_DIR=str(root / "cache"),
            # uv permits local Git fetches; indexes/build requirements stay offline.
            UV_OFFLINE="false",
            UV_PYTHON_DOWNLOADS="never",
            PIPX_HOME=str(root / "pipx"),
            PIPX_BIN_DIR=str(root / "bin"),
            PIPX_LOG_DIR=str(root / "logs"),
            PIPX_MAN_DIR=str(root / "man"),
            PIPX_DEFAULT_PYTHON=sys.executable,
            PIP_NO_INDEX="1",
            PIP_FIND_LINKS=str(wheelhouse),
            PIP_DISABLE_PIP_VERSION_CHECK="1",
        )
        env.update(isolated_agent_env(root))
        config = root / "uv.toml"
        config.write_text(
            "no-index = true\nfind-links = [" + json.dumps(wheelhouse.as_posix()) + "]\n"
        )
        env["UV_CONFIG_FILE"] = str(config)
        source = "git+" + repo.as_uri()
        if manager == "venv":
            prefix = root / "standalone space"
            venv.EnvBuilder(with_pip=True).create(prefix)
            python = prefix / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
            command = [str(python), "-m", "pip", "install", source + "@" + before]
        elif manager == "uv":
            prefix = root / "tools/yicloud-skill"
            command = ["uv", "tool", "install", "--python", sys.executable, source + "@" + before]
        else:
            prefix = root / "pipx/venvs/yicloud-skill"
            command = ["pipx", "install", source + "@" + before]
        subprocess.run(command, env=env, cwd=root, check=True, capture_output=True)
        python = prefix / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        cli = prefix / ("Scripts/yicloud.exe" if os.name == "nt" else "bin/yicloud")

        def run(args, check=True):
            result = subprocess.run(
                args, env=env, cwd=root, text=True, encoding="utf-8", capture_output=True
            )
            if check and result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            return result

        def fixture_provenance(commit):
            data = {
                "url": REPOSITORY,
                "vcs_info": {"vcs": "git", "requested_revision": "main", "commit_id": commit},
            }
            run(
                [
                    str(python),
                    "-I",
                    "-c",
                    'from importlib.metadata import distribution; from pathlib import Path; import sys; Path(distribution("yicloud-skill")._path, "direct_url.json").write_text(sys.argv[1], encoding="utf-8")',
                    json.dumps(data),
                ]
            )

        def fixture_discovery():
            release = dict(
                version=version, commit=after, channel="github-main", spec=source + "@" + after
            )
            run(
                [
                    str(python),
                    "-I",
                    "-c",
                    'from pathlib import Path; import yicloud.update as u, sys; p=Path(u.__file__); p.write_text(p.read_text(encoding="utf-8") + sys.argv[1], encoding="utf-8")',
                    f"\nlatest_source = lambda: {release!r}\n",
                ]
            )

        fixture_provenance(before)
        fixture_discovery()
        (root / "codex").mkdir()
        (root / ".cursor").mkdir()
        run([str(cli), "skill", "install"])
        skill = root / "codex/skills/yicloud/SKILL.md"
        assert b"Initial fixture commit" in skill.read_bytes()
        assert (root / ".cursor/skills/yicloud/SKILL.md").exists()
        config_bytes = b'{"accounts": {}, "connections": {}, "contexts": {}, "sentinel": "keep"}'
        (root / "config.json").write_bytes(config_bytes)
        command = [str(cli), "--json", "update"]
        report = json.loads(run([*command, "--check"]).stdout)["data"]
        assert report["installation"]["manager"] == manager, report
        assert report["update_available"]
        assert report["current_version"] == report["latest_version"]
        assert report["current_commit"] == before and report["latest_commit"] == after
        original = skill.read_bytes()
        skill.write_bytes(b"user edits")
        blocked = run(command, check=False)
        assert blocked.returncode != 0 and skill.read_bytes() == b"user edits"
        skill.write_bytes(original)
        data = json.loads(run(command).stdout)
        if os.name == "nt":
            assert data["data"]["state"] == "started" and not data["data"]["completed"]
            result_path = Path(data["data"]["result"])
            deadline = time.monotonic() + 60
            while not result_path.exists() and time.monotonic() < deadline:
                time.sleep(0.1)
            data = json.loads(result_path.read_text())
        assert data["ok"], data
        assert data["data"]["commit"] == after and data["data"]["version"] == version
        assert len(data["data"]["skills"]) == 2
        assert all(row["state"] == "matching" for row in data["data"]["skills"])
        assert b"Initial fixture commit" not in skill.read_bytes()
        assert (root / "config.json").read_bytes() == config_bytes
        assert not (root / ".claude").exists()
        fixture_provenance(after)
        fixture_discovery()
        stamp = skill.stat().st_mtime_ns
        current = json.loads(run(command).stdout)["data"]
        assert not current["update_available"] and current["state"] == "current"
        assert skill.stat().st_mtime_ns == stamp
        assert not list(prefix.parent.glob(".*-yicloud-update.lock"))
        print(
            f"{manager}: same-version Git commit update, real console handoff, detected-Agent sync, edit protection, config preservation and no-op repeat passed"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dist", type=Path)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--manager", choices=["uv", "pipx", "venv", "all"], default="all")
    args = parser.parse_args()
    wheels = list(args.dist.glob("*.whl"))
    assert len(wheels) == 1
    managers = ["uv", "pipx", "venv"] if args.manager == "all" else [args.manager]
    for selected in managers:
        if selected != "venv" and not shutil.which(selected):
            raise SystemExit(f"Required manager missing: {selected}")
        verify(wheels[0].resolve(), args.wheelhouse.resolve(), selected)
