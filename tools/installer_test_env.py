"""Keep test managers available without exposing the developer's existing CLI on PATH."""

import os
import shutil
import sys
from pathlib import Path


def isolated_path(root):
    directory = root / "manager-bin"
    directory.mkdir()
    for name in ("uv", "pipx"):
        executable = shutil.which(name)
        if executable:
            shutil.copy2(executable, directory / Path(executable).name)
    paths = [str(directory), str(Path(sys._base_executable).parent)]
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if entry and not any((Path(entry) / name).exists() for name in ("yicloud", "yicloud.exe")):
            paths.append(entry)
    return os.pathsep.join(paths)
