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
            if (
                not p.parts
                or p.is_absolute()
                or p.as_posix() != name
                or ".." in p.parts
                or "\\" in name
                or ":" in name
                or "\x00" in name
                or p.parts[0] == MARKER
            ):
                raise ValueError()
        return value["files"]
    except (ValueError, KeyError, TypeError) as e:
        raise ConfigurationError(f"Invalid YicloudSkill ownership manifest at {path}") from e


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def packaged_files(source):
    """Match distributed instructions and Python helpers, including source checkouts."""
    return {
        p.relative_to(source).as_posix(): digest(p)
        for p in source.rglob("*")
        if p.is_file()
        and not p.is_symlink()
        and (p.suffix in {".md", ".yaml"} or (p.parent == source / "scripts" and p.suffix == ".py"))
    }


def checked_root(root):
    """Check the nearest existing parent before any target is changed."""
    for path in (root, *root.parents):
        if path.exists() or path.is_symlink():
            if not path.is_dir():
                raise ConfigurationError(f"Skill directory conflicts with non-directory: {path}")
            break


def checked_path(root, name, *, require_file=False):
    dest = root / name
    for p in (dest, *dest.parents):
        if p == root:
            break
        if p.is_symlink():
            raise ConfigurationError(f"Skill path conflicts with symlink: {p}")
        if p == dest:
            if require_file and p.exists() and not p.is_file():
                raise ConfigurationError(f"Skill file conflicts with non-file: {p}")
        elif p.exists() and not p.is_dir():
            raise ConfigurationError(f"Skill parent conflicts with non-directory: {p}")
    return dest


def install(target, path=None, uninstall=False, *, destinations=None, preflight=False):
    destinations = targets(target, path) if destinations is None else list(destinations)
    previous = {}
    source = Path(str(files("yicloud").joinpath("skill")))
    packaged = packaged_files(source)
    for dest in destinations:
        old = manifest(dest) if dest.exists() or dest.is_symlink() else {}
        checked_root(dest)
        previous[dest] = old
        for name in old.keys() | packaged.keys():
            checked_path(dest, name, require_file=not uninstall)
        if not uninstall:
            # Preflight every target before changing any installation.
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
    if preflight:
        return [str(p) for p in destinations]
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
        if old == packaged and all(
            (dest / name).is_file() and digest(dest / name) == expected
            for name, expected in packaged.items()
        ):
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        stage = Path(tempfile.mkdtemp(prefix=".yicloud-skill-", dir=dest.parent))
        try:
            if dest.exists():
                shutil.copytree(dest, stage, dirs_exist_ok=True, symlinks=True)
            for name in old.keys() - packaged.keys():
                (stage / name).unlink(missing_ok=True)
            for name, expected in packaged.items():
                item = stage / name
                item.parent.mkdir(parents=True, exist_ok=True)
                if not item.is_file() or digest(item) != expected:
                    shutil.copy2(source / name, item)
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


def status(target, path=None):
    """Compare installed content with both its ownership manifest and this package."""
    source = Path(str(files("yicloud").joinpath("skill")))
    packaged = packaged_files(source)
    fingerprint = hashlib.sha256(
        json.dumps(packaged, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    rows = []
    for dest in targets(target, path):
        row = {
            "path": str(dest),
            "state": "missing",
            "missing": [],
            "different": [],
            "local_edits": [],
            "obsolete": [],
        }
        try:
            checked_root(dest)
            if dest.exists() or dest.is_symlink():
                old = manifest(dest)
                for name in old.keys() | packaged.keys():
                    item = checked_path(dest, name, require_file=True)
                    if not item.is_file():
                        if name in packaged:
                            row["missing"].append(name)
                        continue
                    actual = digest(item)
                    if name in old and actual != old[name]:
                        row["local_edits"].append(name)
                    if name in packaged and actual != packaged[name]:
                        row["different"].append(name)
                    if name not in packaged:
                        row["obsolete"].append(name)
                row["state"] = (
                    "matching"
                    if not any(row[k] for k in ("missing", "different", "local_edits", "obsolete"))
                    else "different"
                )
        except (ConfigurationError, OSError) as e:
            row.update(state="conflict", reason=str(e))
        for k in ("missing", "different", "local_edits", "obsolete"):
            row[k].sort()
        rows.append(row)
    return {"package_skill_path": str(source), "package_digest": fingerprint, "targets": rows}


def registry_path():
    # Separate from credentials; custom --path installations are discoverable on update.
    from .config import config_path

    config = config_path()
    return config.with_name(config.name + ".skills.json")


def registered_paths():
    path = registry_path()
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, list) or not all(
            isinstance(p, str) and Path(p).is_absolute() for p in value
        ):
            raise ValueError()
        return [Path(p) for p in value]
    except (OSError, ValueError) as e:
        raise ConfigurationError(f"Invalid skill installation registry: {path}") from e


def remember_path(path, uninstall=False):
    paths = set(registered_paths())
    path = Path(path).expanduser().absolute()
    if uninstall:
        paths.discard(path)
    else:
        paths.add(path)
    registry = registry_path()
    registry.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".skill-installs-", dir=registry.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(sorted(str(p) for p in paths), stream)
        os.replace(temporary, registry)
    finally:
        Path(temporary).unlink(missing_ok=True)


def existing_paths():
    paths = dict.fromkeys([*targets("all"), *registered_paths()])
    # An unowned same-name directory is a conflict, never silently adopted.
    return [p for p in paths if p.exists() or p.is_symlink()]


def sync_existing(paths=None):
    paths = existing_paths() if paths is None else [Path(p) for p in paths]
    install("all", destinations=paths)
    rows = [status("codex", p)["targets"][0] for p in paths]
    if any(row["state"] != "matching" for row in rows):
        raise ConfigurationError("Skill synchronization verification failed; run skill status")
    return rows
