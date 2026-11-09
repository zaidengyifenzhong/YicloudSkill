# YicloudSkill

## Overview

YicloudSkill 通过标准 Agent Skills 为支持该格式的 Agent 提供操作[仪电智算云](https://api.yicloud.com.cn/)的 Agent Skill，同时提供独立的 Python SDK 和 `yicloud` CLI。CLI、SDK、内置 Skill 从同一 GitHub 仓库分发；默认安装和更新跟踪 `main`，每次更新固定到检查到的完整提交 SHA。

## Features

- 查询项目、可用区、镜像、存储及计算规格。
- 管理开发机、训练 Job，检查任务状态、日志及产物。
- 通过 SSH/SFTP/SCP 执行远程命令和传输文件。
- 提供 Ray、模型部署等接口及本地请求校验；实际联测范围见下文。
- 管理本地账号和工作上下文，检查安装状态，统一更新 CLI 与已有 Skill。

Agent Skill 提供操作流程与参数指引；CLI 和 Python SDK 负责调用 API，可以单独使用。

## Installation

要求 Python 3.10+ 和 Git。项目通过 GitHub 分发。uv 和 pipx 是可选安装管理器，也可使用 Python 自带的 venv。**选择一种方式安装**，避免多套 CLI 争用 PATH。

### 安装脚本

先检出并检查脚本，再执行；无需管道执行远程脚本：

```sh
git clone https://github.com/zaidengyifenzhong/YicloudSkill.git
cd YicloudSkill
```

Linux / macOS：

```sh
bash install.sh
# 不使用 uv/pipx
bash install.sh --manager venv
```

Windows PowerShell：

```powershell
.\install.ps1
.\install.ps1 -Manager venv
```

脚本默认从官方 GitHub `main` 安装 CLI，**自动检测本机已有 Agent，只为检测到的 Agent 安装 Skill**。没有检测到 Agent 时只安装 CLI，并显示后续选择方式，不创建任何 Agent 目录。脚本会验证 CLI、Skill 和 `doctor local`；失败返回非零退出码。

`auto` 优先复用 `~/.local/share/yicloud-skill/venv`，否则选择已有 uv、pipx，均不存在时创建该独立 venv。POSIX 需要 `python3`，Windows 需要 PATH 中的 `python`；部分 Linux 发行版需通过系统包管理器提供 venv 支持。可用 `--venv PATH` / `-Venv PATH` 指定环境，`--target none` / `-Target none` 只安装 CLI。

若 PATH 已有另一套 CLI，脚本会停止并给出位置。安装后按提示将 CLI 目录加入 PATH；uv 用户可运行 `uv tool update-shell`，pipx 用户可运行 `pipx ensurepath`，然后重新打开终端。

### 直接使用 uv 或 pipx

Linux、macOS、Windows（PowerShell）均可使用以下一种方式：

```sh
uv tool install 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
```

或：

```sh
pipx install 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
```

随后自动配置已检测到的 Agent 并验证：

```sh
yicloud skill agents
yicloud skill install
yicloud skill status
yicloud --version
yicloud doctor local
```

仅安装 Python 包不会创建 Agent 目录。Skill 使用标准 `SKILL.md`、参考文档和脚本，面向所有兼容 Agent Skills 的工具；已内置 Codex、Claude Code、Cursor、Gemini CLI、Copilot、OpenCode、Windsurf 等多种 Agent 的目录检测。完整目录规则见 [Agent 支持说明](AGENT_SUPPORT.md)。

`skill agents` 只读取目录是否存在，列出检测结果和目标路径，不运行 Agent 或读取其配置内容。默认 `auto` 和 `all` 都表示检测到的 Agent；共享同一技能目录时只写入一次。尚未生成配置目录的 Agent 可显式选择：

```sh
yicloud skill install --target cursor --target gemini-cli
# 原有名称仍支持
yicloud skill install --target codex
yicloud skill install --target claude
# 其他兼容 Agent 的自定义技能目录
yicloud skill install --target custom --path /path/to/agent/skills/yicloud
```

显式目标表示用户选择该 Agent，允许创建相应 Skill 目录；自定义路径会单独登记以便自动更新。默认 Codex 使用标准 `~/.agents/skills/yicloud`，已有旧路径或显式 `CODEX_HOME` 会继续使用相应路径；Claude Code 支持 `CLAUDE_CONFIG_DIR`。目录冲突和本地修改不会静默覆盖。

## Quick Start

添加已有云平台账号的本地配置并验证连接：

```sh
yicloud account add research --auth hmac --host https://gate.yicloud.com.cn
yicloud account use research
yicloud account check
yicloud project list
yicloud resources zones
```

`account add` 不会注册云平台账号。`research` 是本地别名，不是请求中的 `Creator` 或 `Project`。

| 控制台 | API 网关 |
| --- | --- |
| `console.yicloud.com.cn` | `https://gate.yicloud.com.cn` |
| `console.yicloud.com` | `https://gate.yicloud.com` |

Token、服务账号及环境变量见[认证说明](src/yicloud/skill/references/access.md)。在已安装 Skill 的 Agent 中提出目标，例如“使用 yicloud，列出当前账号项目和可用 GPU 规格”。创建、停止或删除资源前应确认资源范围。

## Updating

```sh
yicloud update --check
yicloud update
```

- `--check` 只读取 GitHub `main` 的提交 SHA、该提交中的版本/Python 要求，以及本地版本、提交、安装管理器和 Skill 状态，不修改文件。
- 默认更新跟踪 `main`，普通代码提交即可供安装和更新。同版本号下提交不同仍会更新；提交相同则跳过包重装，同时检查已有 Skill 的同步状态。本地包版本更高时不会自动降级。
- 检查后固定到完整 SHA 安装，避免检查与安装之间分支变化导致版本错位；完成后核对实际安装的版本和提交。
- 使用当前 uv、pipx 或带 pip 的独立 venv，不创建第二套 CLI。Git、原管理器缺失、环境冲突、网络失败、GitHub 限流或 Python 不兼容均明确报错。editable、本地 wheel、自定义来源和无法识别来源的安装不自动改写，按原安装流程维护。
- 只同步已安装的 Skill，包括已登记的自定义目录；不会因为新检测到 Agent 而擅自创建新的 Skill。要为新 Agent 安装时重新运行 `yicloud skill install`。
- 本地 Skill 修改或同名目录冲突会阻止更新，需先备份并移走冲突文件。未变化的 Skill 不重复复制。
- 包更新在临时辅助进程中执行。POSIX 替换原 CLI 进程；Windows 等待 Python 和 `.exe` 启动器退出后更新，首次返回 `started, completed: false`，须按输出路径查看 `result.json` 的 `ok: true` 确认完成。
- 包安装、CLI 入口、版本、提交与 Skill 校验全部成功才报告完成。失败不承诺回滚，可能需要按输出的原环境命令修复；中断残留锁仅在确认无更新进程后移除。

账号、认证和 context 配置不会被更新过程重写。自定义 Skill 路径独立存储在账号配置文件旁的 `config.json.skills.json`（文件名随 `YICLOUD_CONFIG` 改变），不含凭据。失败日志位于用户私有临时目录，排查后可删除。

`skill status` 是离线同步检查，`matching` 只表示与本地内置 Skill 一致；远端提交请使用 `update --check`。卸载 Skill 仅移除受管理且哈希未变的文件：

```sh
yicloud skill uninstall --target cursor
```

## CLI Usage

```sh
yicloud --help
yicloud api list --service job
yicloud api describe job CreateJob
yicloud job create --file job.json --dry-run
yicloud job create --file job.json
yicloud job logs JOB_ID --project PROJECT --zone ZONE --follow
yicloud context set lab --account research --project PROJECT --zone ZONE
yicloud context use lab
yicloud context show
yicloud doctor local
```

将占位符替换为实际资源标识。`--dry-run` 仅验证固定 SDK 的本地请求结构，不验证权限、余量或任务是否可运行。显式参数优先于 context；`--no-context` 可忽略当前上下文，请求文件和通用 API 不自动补入项目与可用区。

SSH 首次连接前需登记公钥，自动连接默认启用 Agent 转发，可用 `--no-forward-agent` 关闭。见 [SSH 指引](src/yicloud/skill/references/workspace/connect.md)及 [CLI 诊断](src/yicloud/skill/references/diagnostics/cli.md)。

## Python SDK

```python
from yicloud import YicloudClient

with YicloudClient.from_account("research") as client:
    result = client.call(
        service="job",
        action="ListJobs",
        params={"Project": "PROJECT", "ZoneId": "ZONE", "Limit": 20},
    )
    print(result.data)
```

SDK 与 CLI 由 `yicloud-skill` 一起分发。`from_account()` 接收本地账号别名，请求参数仍需符合具体 API。依赖 SDK 的应用应通过自己的项目依赖管理流程升级，系统环境和 editable 安装不自动自更新。

## Development

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m ruff check src tests tools
.venv/bin/python -m ruff format --check src tests tools
.venv/bin/python -m pytest -q
.venv/bin/python -m build
.venv/bin/python tools/check_release.py
```

Windows 使用 `.venv\Scripts\python.exe`。CI 覆盖 Python 3.10、3.11、3.12 与 Linux、macOS、Windows，检查 lint、测试、Skill、wheel/sdist 内容、隔离安装及真实管理器的离线更新交接。`tools/check_updater.py` 使用临时 Git 仓库的同版本不同提交，验证更新、提交核对和多 Agent 同步；所有写入限于临时目录，不需要真实云账号。

## Release Process

默认分发直接使用 GitHub `main`，不要求先发布版本。包版本唯一来源是 `pyproject.toml`；日常提交可保持同一版本，更新器通过提交 SHA 识别代码变化。

需要可复现的版本快照时，维护者可创建匹配包版本的 `vX.Y.Z` tag，触发跨平台 CI、包构建和 GitHub Release，并上传 wheel/sdist。工作流仅上传 GitHub Release 产物。详见 [RELEASING.md](RELEASING.md)。

## Documentation

| 文档 | 内容 |
| --- | --- |
| [Skill 任务导航](src/yicloud/skill/SKILL.md) | 开发机、Job、镜像、存储、Ray、模型部署 |
| [认证配置](src/yicloud/skill/references/access.md) | HMAC、Token、多账号与环境变量 |
| [训练任务与产物](src/yicloud/skill/references/jobs/observe.md) | 日志和产物 |
| [存储](src/yicloud/skill/references/storage.md) | 存储资源 |
| [镜像](src/yicloud/skill/references/images/query.md) | 镜像查询 |
| [API 与错误处理](src/yicloud/skill/references/diagnostics/api.md) | 通用 API 与排错 |
| [发布维护](RELEASING.md) | 发布配置、验证和故障处理 |

## Compatibility & Limitations

- API 目录固定于仪电智算云 Go SDK v0.5.1，不覆盖控制台全部路由。原有公开 SDK 接口和业务 CLI 保持兼容。
- 不支持网页终端及 WebSocket 实时日志；`job logs --follow` 使用轮询。
- 历史真实联测覆盖 `.com.cn` HMAC、部分资源查询、macOS SSH/SFTP、临时 CPU 开发机创建/等待/删除，以及单副本 CPU Job 创建、运行、日志、跨任务 GPFS 产物验证、停止和删除。
- GPU、多副本 Job、Ray/Serving 写操作、Token 与服务账号认证尚未完成联机验证。命令存在不代表已验证所有平台行为。
- 等待超时不会自动停止远端任务；SCP 使用完整文件复制。
- 更新需要可访问官方 GitHub、Git、原安装管理器及当前环境写权限；不使用 sudo，不安装缺失的管理器，不处理系统包管理器维护的 Python。
- Windows 更新异步完成；原生 Windows 行为应以该平台 CI/实测结果为准。自动更新跟踪官方 `main`；显式安装 tag 后运行 `update` 也会切换到 `main`。

## License

[MIT](LICENSE)。项目设计参考 InspireSkill，详见[第三方声明](THIRD_PARTY.md)。
