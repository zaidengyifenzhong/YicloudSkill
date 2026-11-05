"""Check that local Markdown targets are files in the distributed Skill."""

import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from yicloud.skill_install import packaged_files


def local_references(root, markdown):
    root = Path(os.path.abspath(root))
    resolved_root = root.resolve()
    distributed = packaged_files(root)
    directories = {parent.as_posix() for name in distributed for parent in Path(name).parents}
    links, broken = 0, []
    for document in markdown:
        for target in re.findall(r"\]\(([^)]+)\)", document.read_text(encoding="utf-8")):
            try:
                drive_path = bool(re.match(r"^[A-Za-z]:[/\\]", target))
                parsed = urlsplit(target)
                if not drive_path and (parsed.scheme or parsed.netloc or not parsed.path):
                    continue
                links += 1
                if drive_path:
                    raise ValueError("Drive-absolute paths are not portable Skill references")
                raw_path = document.parent / unquote(parsed.path)
                candidate = Path(os.path.abspath(raw_path))
                relative = candidate.relative_to(root).as_posix()
                valid = (
                    raw_path.resolve().is_relative_to(resolved_root)
                    and raw_path.is_file()
                    and not raw_path.is_symlink()
                    and relative in distributed
                )
                # Even prefixes cancelled by '..' must survive Skill installation.
                for parent in raw_path.parents:
                    if parent == root:
                        break
                    directory = Path(os.path.abspath(parent)).relative_to(root).as_posix()
                    if parent.is_symlink() or directory not in directories:
                        valid = False
                        break
            except (OSError, ValueError, RuntimeError):
                valid = False
            if not valid:
                broken.append({"file": document.relative_to(root).as_posix(), "target": target})
    return links, broken
