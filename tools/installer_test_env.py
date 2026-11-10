"""Keep test managers available without exposing the developer's existing CLI on PATH."""

import os
import shutil
import sys
from pathlib import Path


def isolated_agent_env(root):
    """Never let automatic detection inherit a developer's real agent roots."""
    return {
        "HOME": str(root),
        "USERPROFILE": str(root),
        "CODEX_HOME": str(root / "codex"),
        "XDG_CONFIG_HOME": str(root / ".config"),
        "CLAUDE_CONFIG_DIR": str(root / ".claude"),
        "HERMES_HOME": str(root / ".hermes"),
        "VIBE_HOME": str(root / ".vibe"),
        "APPDATA": str(root / "AppData/Roaming"),
        "LOCALAPPDATA": str(root / "AppData/Local"),
        "FLATPAK_XDG_CONFIG_HOME": str(root / ".flatpak-config"),
    }


def isolated_path(root):
    directory = root / "manager-bin"
    directory.mkdir()
    for name in ("uv", "pipx"):
        executable = shutil.which(name)
        if executable:
            shutil.copy2(executable, directory / Path(executable).name)
    for name in ("python", "python3"):
        if os.name == "nt":
            (directory / f"{name}.cmd").write_text(
                f'@"{sys._base_executable}" %*\n', encoding="utf-8"
            )
        else:
            (directory / name).symlink_to(sys._base_executable)
    paths = [str(directory)]
    for entry in [str(Path(sys._base_executable).parent), *os.get_exec_path()]:
        if entry and not any((Path(entry) / name).exists() for name in ("yicloud", "yicloud.exe")):
            paths.append(entry)
    return os.pathsep.join(paths)
