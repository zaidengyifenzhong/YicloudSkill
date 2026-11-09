"""User-level Agent Skills discovery; never creates directories during detection.

Directory conventions are maintained alongside the Agent Skills ecosystem:
https://github.com/vercel-labs/skills/blob/main/src/agents.ts
No agent executable is launched and no configuration contents are read.
"""

import os
from pathlib import Path

# (CLI name, configuration directory, global skills directory).
# Prefix @ resolves against XDG_CONFIG_HOME, otherwise paths are under HOME.
LAYOUTS = (
    ("universal", ".agents", ".agents/skills"),
    ("claude", ".claude", ".claude/skills"),
    ("cursor", ".cursor", ".cursor/skills"),
    ("gemini-cli", ".gemini", ".gemini/skills"),
    ("github-copilot", ".copilot", ".copilot/skills"),
    ("opencode", "@opencode", "@opencode/skills"),
    ("windsurf", ".codeium/windsurf", ".codeium/windsurf/skills"),
    ("cline", ".cline", ".agents/skills"),
    ("roo", ".roo", ".roo/skills"),
    ("qwen-code", ".qwen", ".qwen/skills"),
    ("kilo", ".kilo", ".kilo/skills"),
    ("kiro-cli", ".kiro", ".kiro/skills"),
    ("trae", ".trae", ".trae/skills"),
    ("trae-cn", ".trae-cn", ".trae-cn/skills"),
    ("amp", "@amp", "@agents/skills"),
    ("goose", "@goose", "@goose/skills"),
    ("crush", "@crush", "@crush/skills"),
    ("droid", ".factory", ".factory/skills"),
    ("junie", ".junie", ".junie/skills"),
    ("zencoder", ".zencoder", ".zencoder/skills"),
    ("openhands", ".openhands", ".openhands/skills"),
    ("pi", ".pi/agent", ".agents/skills"),
    ("warp", ".warp", ".agents/skills"),
    ("qoder", ".qoder", ".qoder/skills"),
    ("pochi", ".pochi", ".pochi/skills"),
    ("neovate", ".neovate", ".neovate/skills"),
    ("adal", ".adal", ".adal/skills"),
    ("iflow-cli", ".iflow", ".iflow/skills"),
    ("mux", ".mux", ".mux/skills"),
    ("aider-desk", ".aider-desk", ".aider-desk/skills"),
    ("augment", ".augment", ".augment/skills"),
    ("codebuddy", ".codebuddy", ".codebuddy/skills"),
    ("codemaker", ".codemaker", ".codemaker/skills"),
    ("codestudio", ".codestudio", ".codestudio/skills"),
    ("command-code", ".commandcode", ".commandcode/skills"),
    ("cortex", ".snowflake/cortex", ".snowflake/cortex/skills"),
    ("deepagents", ".deepagents", ".deepagents/agent/skills"),
    ("devin", "@devin", "@devin/skills"),
    ("dexto", ".dexto", ".agents/skills"),
    ("firebender", ".firebender", ".firebender/skills"),
    ("forgecode", ".forge", ".forge/skills"),
    ("fx", ".fx", ".agents/skills"),
)
ALIASES = {"claude-code": "claude", "gemini": "gemini-cli", "copilot": "github-copilot"}
SPECIAL = ("codex", "openclaw", "hermes-agent", "mistral-vibe", "antigravity", "zed")
AGENT_NAMES = tuple(sorted([*SPECIAL, *(row[0] for row in LAYOUTS)]))
TARGET_NAMES = ("auto", "all", *AGENT_NAMES, *ALIASES, "custom")


def configured_root(variable, fallback):
    value = os.environ.get(variable, "").strip()
    return Path(value).expanduser().absolute() if value else fallback


def inventory():
    home = Path.home()
    config = configured_root("XDG_CONFIG_HOME", home / ".config")

    def resolve(path):
        return config / path[1:] if path.startswith("@") else home / path

    rows = {}
    for name, evidence, skills in LAYOUTS:
        root = resolve(evidence)
        skills = resolve(skills)
        if name == "claude":
            root = configured_root("CLAUDE_CONFIG_DIR", root)
            skills = root / "skills"
        detected = root.is_dir()
        if name == "kilo":
            detected = detected or (home / ".kilocode").is_dir()
        rows[name] = dict(name=name, detected=detected, path=str(skills / "yicloud"))
    codex = configured_root("CODEX_HOME", home / ".codex")
    canonical = home / ".agents/skills/yicloud"
    legacy = codex / "skills/yicloud"
    # Preserve existing managed paths and explicitly configured CODEX_HOME.
    codex_path = (
        legacy
        if legacy.exists() or legacy.is_symlink() or os.getenv("CODEX_HOME", "").strip()
        else canonical
    )
    rows["codex"] = dict(name="codex", detected=codex.is_dir(), path=str(codex_path))
    for name, variable, fallback in (
        ("hermes-agent", "HERMES_HOME", home / ".hermes"),
        ("mistral-vibe", "VIBE_HOME", home / ".vibe"),
    ):
        root = configured_root(variable, fallback)
        rows[name] = dict(name=name, detected=root.is_dir(), path=str(root / "skills/yicloud"))
    claw = next(
        (home / p for p in (".openclaw", ".clawdbot", ".moltbot") if (home / p).is_dir()),
        home / ".openclaw",
    )
    rows["openclaw"] = dict(
        name="openclaw", detected=claw.is_dir(), path=str(claw / "skills/yicloud")
    )
    rows["antigravity"] = dict(
        name="antigravity",
        detected=(home / ".gemini/antigravity").is_dir()
        or (home / ".gemini/antigravity-cli").is_dir(),
        path=str(home / ".gemini/config/skills/yicloud"),
    )
    zed_roots = [config / "zed"]
    for variable, folder in (("APPDATA", "Zed"), ("FLATPAK_XDG_CONFIG_HOME", "zed")):
        if os.environ.get(variable):
            zed_roots.append(Path(os.environ[variable]) / folder)
    rows["zed"] = dict(name="zed", detected=any(p.is_dir() for p in zed_roots), path=str(canonical))
    return [rows[name] for name in AGENT_NAMES]


def detected_agents():
    return [row for row in inventory() if row["detected"]]


def candidate_paths():
    """Include legacy locations even if the corresponding agent was removed."""
    home = Path.home()
    legacy = configured_root("CODEX_HOME", home / ".codex") / "skills/yicloud"
    return list(
        dict.fromkeys(
            [*(Path(row["path"]) for row in inventory()), legacy, home / ".agents/skills/yicloud"]
        )
    )
