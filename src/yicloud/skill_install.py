import hashlib
import json
import os
import shutil
import tempfile
from importlib.resources import files
from pathlib import Path, PurePosixPath

from .errors import ConfigurationError

MARKER = ".yicloud-managed"
OWNER = "YicloudSkill/skill/v1"


def targets(target, path=None):
    if path:
        if target == "all":
            raise ConfigurationError("Explicit --path requires one target")
        return [Path(path).expanduser()]
    roots = {
        "codex": Path(os.getenv("CODEX_HOME", str(Path.home() / ".codex"))) / "skills/yicloud",
        "claude": Path.home() / ".claude/skills/yicloud",
    }
    return list(roots.values()) if target == "all" else [roots[target]]


def manifest(path):
    marker = path / MARKER
    if path.is_symlink() or marker.is_symlink() or not marker.is_file():
        raise ConfigurationError(
            f"Skill conflict at {path}; existing content is not managed by YicloudSkill"
        )
    try:
        value = json.loads(marker.read_text(encoding="utf-8"))
        if value["owner"] != OWNER or not isinstance(value["files"], dict):
            raise ValueError()
        for name in value["files"]:
            p = PurePosixPath(name)
            if p.is_absolute() or ".." in p.parts or "\\" in name:
                raise ValueError()
        return value["files"]
    except (ValueError, KeyError, TypeError) as e:
        raise ConfigurationError(f"Invalid YicloudSkill ownership manifest at {path}") from e


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked_path(root, name):
    dest = root / name
    for p in (dest, *dest.parents):
        if p == root:
            break
        if p.is_symlink():
            raise ConfigurationError(f"Skill path conflicts with symlink: {p}")
    return dest


def install(target, path=None, uninstall=False):
    destinations = targets(target, path)
    previous = {}
    source = Path(str(files("yicloud").joinpath("skill")))
    packaged = {
        p.relative_to(source).as_posix(): digest(p) for p in source.rglob("*") if p.is_file()
    }
    for dest in destinations:
        old = manifest(dest) if dest.exists() or dest.is_symlink() else {}
        previous[dest] = old
        for name in old.keys() | packaged.keys():
            checked_path(dest, name)
    for dest in destinations:
        old = previous[dest]
        if uninstall:
            for name, expected in old.items():
                item = checked_path(dest, name)
                if item.is_file() and digest(item) == expected:
                    item.unlink()
            if dest.exists():
                (dest / MARKER).unlink(missing_ok=True)
                for directory in sorted(
                    (p for p in dest.rglob("*") if p.is_dir() and not p.is_symlink()),
                    key=lambda p: len(p.parts),
                    reverse=True,
                ):
                    if not any(directory.iterdir()):
                        directory.rmdir()
                if not any(dest.iterdir()):
                    dest.rmdir()
            continue
        # Refuse to overwrite edits to files from a previous installation.
        for name, expected in old.items():
            item = dest / name
            if item.is_file() and digest(item) != expected:
                raise ConfigurationError(
                    f"Installed skill file has local edits: {item}; move it before upgrading"
                )
        for name in packaged.keys() - old.keys():
            if (dest / name).exists():
                raise ConfigurationError(
                    f"Unmanaged file conflicts with packaged skill: {dest / name}"
                )
        dest.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".yicloud-skill-", dir=dest.parent))
        try:
            if dest.exists():
                shutil.copytree(dest, stage, dirs_exist_ok=True, symlinks=True)
            for name in old.keys() - packaged.keys():
                (stage / name).unlink(missing_ok=True)
            shutil.copytree(source, stage, dirs_exist_ok=True)
            (stage / MARKER).write_text(
                json.dumps({"owner": OWNER, "files": packaged}), encoding="utf-8"
            )
            if dest.exists():
                backup = stage.with_name(stage.name + "-previous")
                dest.rename(backup)
                try:
                    stage.rename(dest)
                except BaseException:
                    backup.rename(dest)
                    raise
                shutil.rmtree(backup)
            else:
                stage.rename(dest)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return [str(p) for p in destinations]
