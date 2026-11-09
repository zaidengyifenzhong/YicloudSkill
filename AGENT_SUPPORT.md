# Agent support

Skill 使用标准 `SKILL.md` 格式。安装默认检测已有用户配置目录，不执行 Agent、不读取配置内容、不扫描研究项目。没有检测到 Agent 时只安装 CLI。

当前内置 48 个目标（包含通用共享目录）。目录规则参考 [Agent Skills 安装生态](https://github.com/vercel-labs/skills/blob/main/src/agents.ts)；路径存在只代表可以安装，不能替代相应 Agent 的实际加载验证。

```sh
yicloud skill agents
yicloud skill install
yicloud skill install --target cursor --target gemini-cli
yicloud skill install --target custom --path /path/to/agent/skills/yicloud
```

`auto` / `all` 选择所有检测到的目标，共享路径去重；显式目标允许创建该目标的 Skill 目录。其他兼容 Agent 可使用 `custom --path`。本地编辑与目录冲突保护适用于所有目标。

| 目标 | 检测目录 | Skill 根目录 |
| --- | --- | --- |
| `adal` | `~/.adal` | `~/.adal/skills` |
| `aider-desk` | `~/.aider-desk` | `~/.aider-desk/skills` |
| `amp` | `$XDG_CONFIG_HOME/amp` | `$XDG_CONFIG_HOME/agents/skills` |
| `augment` | `~/.augment` | `~/.augment/skills` |
| `claude` | `~/.claude` | `~/.claude/skills` |
| `cline` | `~/.cline` | `~/.agents/skills` |
| `codebuddy` | `~/.codebuddy` | `~/.codebuddy/skills` |
| `codemaker` | `~/.codemaker` | `~/.codemaker/skills` |
| `codestudio` | `~/.codestudio` | `~/.codestudio/skills` |
| `command-code` | `~/.commandcode` | `~/.commandcode/skills` |
| `cortex` | `~/.snowflake/cortex` | `~/.snowflake/cortex/skills` |
| `crush` | `$XDG_CONFIG_HOME/crush` | `$XDG_CONFIG_HOME/crush/skills` |
| `cursor` | `~/.cursor` | `~/.cursor/skills` |
| `deepagents` | `~/.deepagents` | `~/.deepagents/agent/skills` |
| `devin` | `$XDG_CONFIG_HOME/devin` | `$XDG_CONFIG_HOME/devin/skills` |
| `dexto` | `~/.dexto` | `~/.agents/skills` |
| `droid` | `~/.factory` | `~/.factory/skills` |
| `firebender` | `~/.firebender` | `~/.firebender/skills` |
| `forgecode` | `~/.forge` | `~/.forge/skills` |
| `fx` | `~/.fx` | `~/.agents/skills` |
| `gemini-cli` | `~/.gemini` | `~/.gemini/skills` |
| `github-copilot` | `~/.copilot` | `~/.copilot/skills` |
| `goose` | `$XDG_CONFIG_HOME/goose` | `$XDG_CONFIG_HOME/goose/skills` |
| `iflow-cli` | `~/.iflow` | `~/.iflow/skills` |
| `junie` | `~/.junie` | `~/.junie/skills` |
| `kilo` | `~/.kilo` | `~/.kilo/skills` |
| `kiro-cli` | `~/.kiro` | `~/.kiro/skills` |
| `mux` | `~/.mux` | `~/.mux/skills` |
| `neovate` | `~/.neovate` | `~/.neovate/skills` |
| `opencode` | `$XDG_CONFIG_HOME/opencode` | `$XDG_CONFIG_HOME/opencode/skills` |
| `openhands` | `~/.openhands` | `~/.openhands/skills` |
| `pi` | `~/.pi/agent` | `~/.agents/skills` |
| `pochi` | `~/.pochi` | `~/.pochi/skills` |
| `qoder` | `~/.qoder` | `~/.qoder/skills` |
| `qwen-code` | `~/.qwen` | `~/.qwen/skills` |
| `roo` | `~/.roo` | `~/.roo/skills` |
| `trae` | `~/.trae` | `~/.trae/skills` |
| `trae-cn` | `~/.trae-cn` | `~/.trae-cn/skills` |
| `universal` | `~/.agents` | `~/.agents/skills` |
| `warp` | `~/.warp` | `~/.agents/skills` |
| `windsurf` | `~/.codeium/windsurf` | `~/.codeium/windsurf/skills` |
| `zencoder` | `~/.zencoder` | `~/.zencoder/skills` |
| `codex` | `$CODEX_HOME` 或 `~/.codex` | 默认 `~/.agents/skills`；已有旧路径或显式 `CODEX_HOME` 时使用对应 `skills` |
| `openclaw` | `~/.openclaw`、`~/.clawdbot`、`~/.moltbot` | 检测到的目录下 `skills` |
| `hermes-agent` | `$HERMES_HOME` 或 `~/.hermes` | 对应目录下 `skills` |
| `mistral-vibe` | `$VIBE_HOME` 或 `~/.vibe` | 对应目录下 `skills` |
| `antigravity` | `~/.gemini/antigravity` 或 `~/.gemini/antigravity-cli` | `~/.gemini/config/skills` |
| `zed` | `$XDG_CONFIG_HOME/zed`、`$APPDATA/Zed`、Flatpak 配置 | `~/.agents/skills` |

每个 Skill 根目录下安装 `yicloud` 子目录。`XDG_CONFIG_HOME` 默认 `~/.config`；Claude Code 支持 `CLAUDE_CONFIG_DIR`；Kilo 兼容 `.kilocode` 检测；别名 `claude-code`、`gemini`、`copilot` 均可使用。

Windows 通过用户主目录和环境变量解析路径。只装有可执行文件、尚未生成配置目录的 Agent 不会自动安装，可显式指定目标。任何未收录的 Agent 只要支持 Agent Skills，都可用自定义路径安装；不宣称已验证所有 Agent 的运行时加载。
