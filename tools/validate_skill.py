"""Portable skill frontmatter, metadata and local-reference validation."""

import re
from pathlib import Path

import yaml

root = Path(__file__).resolve().parents[1] / "src/yicloud/skill"
entry = (root / "SKILL.md").read_text(encoding="utf-8")
frontmatter = yaml.safe_load(entry.split("---", 2)[1])
assert frontmatter["name"] == "yicloud"
assert frontmatter["description"]
assert len(entry.splitlines()) < 100
metadata = yaml.safe_load((root / "agents/openai.yaml").read_text(encoding="utf-8"))
assert "$yicloud" in metadata["interface"]["default_prompt"]
for path in root.rglob("*.md"):
    content = path.read_text(encoding="utf-8")
    assert "TODO" not in content and "[INSERT" not in content
    for target in re.findall(r"\]\(([^)]+)\)", content):
        if "://" not in target and not target.startswith("#"):
            assert (path.parent / target.split("#")[0]).exists(), (path, target)
print("Skill valid: frontmatter, metadata and local references")
