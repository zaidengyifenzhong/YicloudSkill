"""Portable skill frontmatter, metadata and local-reference validation."""

from pathlib import Path

import yaml

from skill_references import local_references


def validate(root):
    entry = (root / "SKILL.md").read_text(encoding="utf-8")
    frontmatter = yaml.safe_load(entry.split("---", 2)[1])
    if frontmatter["name"] != "yicloud" or not frontmatter["description"]:
        raise ValueError("Invalid Skill name or description")
    if len(entry.splitlines()) >= 100:
        raise ValueError("Skill entry must have fewer than 100 lines")
    metadata = yaml.safe_load((root / "agents/openai.yaml").read_text(encoding="utf-8"))
    if "$yicloud" not in metadata["interface"]["default_prompt"]:
        raise ValueError("Skill default prompt must invoke $yicloud")
    markdown = sorted(root.rglob("*.md"))
    for path in markdown:
        content = path.read_text(encoding="utf-8")
        if "TODO" in content or "[INSERT" in content:
            raise ValueError(f"Unfinished Skill content: {path}")
    _, broken = local_references(root, markdown)
    if broken:
        raise ValueError(f"Invalid local Skill references: {broken}")


if __name__ == "__main__":
    validate(Path(__file__).resolve().parents[1] / "src/yicloud/skill")
    print("Skill valid: frontmatter, metadata and local references")
