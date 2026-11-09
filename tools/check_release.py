"""Validate release identity and exact wheel/sdist Skill contents (stdlib only)."""

import argparse
import email
import re
import tarfile
import zipfile
from pathlib import Path


def check(root, dist, tag=None):
    text = (root / "pyproject.toml").read_text(encoding="utf-8")
    version = re.search(r'^version = "([^"]+)"$', text, re.M)[1]
    assert re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", version), version
    if tag:
        assert tag == f"v{version}", f"Tag {tag!r} does not match package v{version}"
    wheels = list(dist.glob("*.whl"))
    sources = list(dist.glob("*.tar.gz"))
    assert len(wheels) == len(sources) == 1, "Expected one wheel and one sdist"
    expected = {
        p.relative_to(root / "src").as_posix(): p.read_bytes()
        for p in (root / "src/yicloud/skill").rglob("*")
        if p.is_file() and p.suffix in {".md", ".yaml", ".py"}
    }
    assert "yicloud/skill/SKILL.md" in expected
    assert "yicloud/skill/agents/openai.yaml" in expected
    assert "yicloud/skill/scripts/request_from_preview.py" in expected
    with zipfile.ZipFile(wheels[0]) as wheel:
        names = wheel.namelist()
        metadata = email.message_from_bytes(
            wheel.read(next(n for n in names if n.endswith("/METADATA")))
        )
        assert metadata["Name"] == "yicloud-skill"
        assert metadata["Version"] == version
        assert metadata["Requires-Python"] == ">=3.10"
        entries = wheel.read(next(n for n in names if n.endswith("/entry_points.txt"))).decode()
        assert "yicloud = yicloud.cli:main" in entries
        for name, content in expected.items():
            assert wheel.read(name) == content, name
        actual = {n for n in names if n.startswith("yicloud/skill/")}
        assert actual == set(expected), actual ^ set(expected)
    with tarfile.open(sources[0]) as source:
        members = {
            m.name.split("/", 1)[1]: m for m in source.getmembers() if "/" in m.name and m.isfile()
        }
        metadata = email.message_from_bytes(source.extractfile(members["PKG-INFO"]).read())
        assert metadata["Version"] == version
        for name, content in expected.items():
            assert source.extractfile(members[f"src/{name}"]).read() == content, name
        for name in (
            "install.sh",
            "install.ps1",
            "pyproject.toml",
            "README.md",
            "RELEASING.md",
            ".github/workflows/release.yml",
            "tools/check_release.py",
            "tests/test_update.py",
        ):
            assert name in members, name
    print(
        f"Validated v{version}: wheel/sdist identity, entry point and {len(expected)} Skill assets"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=Path("dist"))
    parser.add_argument("--tag")
    arguments = parser.parse_args()
    check(Path(__file__).resolve().parents[1], arguments.dist, arguments.tag)
