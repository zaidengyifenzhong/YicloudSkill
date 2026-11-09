# YicloudSkill

## Overview

YicloudSkill 为 Codex 和 Claude Code 提供操作[仪电智算云](https://api.yicloud.com.cn/)的 Agent Skill，同时提供独立的 Python SDK 和 `yicloud` CLI。CLI、SDK、内置 Skill 使用同一个 Python 包版本发布，Git tag 格式为 `vX.Y.Z`。

## Features

- 查询项目、可用区、镜像、存储及计算规格。
- 管理开发机、训练 Job，检查任务状态、日志及产物。
- 通过 SSH/SFTP/SCP 执行远程命令和传输文件。
- 提供 Ray、模型部署等接口及本地请求校验；实际联测范围见下文。
- 管理本地账号和工作上下文，检查安装状态，统一更新 CLI 与已有 Skill。

Agent Skill 提供操作流程与参数指引；CLI 和 Python SDK 负责调用 API，可以单独使用。

## Installation

要求 Python 3.10+。uv 和 pipx 是可选安装管理器，普通用户安装不需要 root 或开发依赖。**选择一种安装方式**，避免多套 `yicloud` 争用 PATH。

### 当前安装方式：GitHub 源码

当前代码已推送到 GitHub `main`，**尚未发布 PyPI 包，也未创建 `v0.4.0` tag 或 GitHub Release**。目前请从 GitHub 安装，不要运行 `uv tool install yicloud-skill` 或 `pipx install yicloud-skill`。

安装额外需要 Git。Linux、macOS、Windows（PowerShell）均可使用以下一种方式：

```sh
uv tool install 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
```

或：

```sh
pipx install 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
```

`main` 是可变的开发来源，包版本号不代表该分支最新提交。正式稳定版发布后将优先通过 PyPI 分发；发布流程见 [RELEASING.md](RELEASING.md)。

选择 Agent 并验证安装：

```sh
yicloud skill install --target codex
yicloud skill status --target codex
yicloud --version
yicloud doctor local
```

将 `codex` 换为 `claude` 或 `all` 可选择 Claude Code 或同时安装。仅安装 Python 包不会创建 Agent 目录。

| Agent | 默认 Skill 目录 |
| --- | --- |
| Codex | `~/.codex/skills/yicloud`，设置 `CODEX_HOME` 后为 `$CODEX_HOME/skills/yicloud` |
| Claude Code | `~/.claude/skills/yicloud` |

`--path` 可指定单个目标的完整 Skill 目录；新安装会记录该路径以供后续自动同步。旧版的自定义路径请重新执行一次带相同 `--path` 的 `skill install`。默认路径中的旧版受管理安装会自动发现。

### 本地安装脚本与独立 venv

先检出并检查脚本，再执行；不需要管道执行远程脚本：

```sh
git clone https://github.com/zaidengyifenzhong/YicloudSkill.git
cd YicloudSkill
```

Linux / macOS：

```sh
bash install.sh --target codex --source 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
# 没有 uv/pipx 时，使用 Python 自带的 venv 和 pip
bash install.sh --manager venv --target codex --source 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
```

Windows PowerShell：

```powershell
.\install.ps1 -Target codex -Source 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
.\install.ps1 -Manager venv -Target codex -Source 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
```

脚本未指定来源时默认请求 PyPI；首次稳定版发布前必须像上面一样显式指定 GitHub 来源。`auto` 优先复用 `~/.local/share/yicloud-skill/venv`，否则选择已有 uv、pipx，均不存在时创建上述独立 venv。POSIX 需要 `python3`，Windows 需要 PATH 中的 `python`；部分 Linux 发行版需先通过系统包管理器提供 Python venv 支持。脚本不会修改其他 Python 环境。可用 `--venv PATH` / `-Venv PATH` 指定独立环境，`--target none` / `-Target none` 只安装 CLI。

脚本会执行 CLI、Skill 和 `doctor local` 验证；任何失败均返回非零退出码。若 PATH 中已有另一套 CLI，脚本会停止并给出位置。按脚本提示将 CLI 所在目录加入 PATH；uv 用户也可运行 `uv tool update-shell`，pipx 用户可运行 `pipx ensurepath`，然后重新打开终端。

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

Token、服务账号及环境变量见[认证说明](src/yicloud/skill/references/access.md)。在 Codex 中可引用 `$yicloud`，例如“使用 $yicloud，列出当前账号项目和可用 GPU 规格”。创建、停止或删除资源前应确认资源范围。

## Updating

### 当前源码安装的更新

首次稳定版尚未发布，`yicloud update --check` 和 `yicloud update` 目前会因找不到远端稳定发行版而报错，不会更新 `main`。当前请按原安装方式更新，**只选择与现有安装对应的一种命令**：

```sh
# uv
uv tool install --force --upgrade 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
# pipx：按其记录的原 GitHub 来源重新安装
pipx reinstall yicloud-skill
# 已有独立 venv；无需安装 uv，强制重装以获取相同包版本下的新提交
"$HOME/.local/share/yicloud-skill/venv/bin/python" -m pip install --upgrade --force-reinstall 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
```

Windows 独立 venv：

```powershell
& "$HOME/.local/share/yicloud-skill/venv/Scripts/python.exe" -m pip install --upgrade --force-reinstall 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
```

随后同步已经选择的 Agent。例如已有 Codex Skill：

```sh
yicloud skill install --target codex
yicloud skill status --target codex
```

Claude Code 使用 `--target claude`，两者均已安装时可用 `--target all`；自定义目录需补充原来的 `--path`。这些命令不会重建账号或 context。

### 首次稳定版发布后的统一更新

正式发布到 PyPI 或官方 GitHub Release 后，日常更新使用：

```sh
yicloud update --check
yicloud update
```

- `--check` 只读取远端版本及本地状态，不修改文件；分别返回当前 CLI 版本、最新兼容稳定版本、安装管理器和 Skill 状态。
- 优先查询 PyPI；仅当 PyPI 项目不存在（HTTP 404）时查询官方 GitHub 最新稳定 Release，并固定其 `vX.Y.Z` tag。网络错误、限流及无兼容版本都会明确失败，不会被当作“已是最新”。
- 支持当前 uv、pipx 和带 pip 的独立 venv；包括没有 uv 的 `~/.local/share/yicloud-skill/venv/`。检测到的管理器必须指向当前环境。系统 Python、editable、自定义来源、缺失管理器或冲突环境会停止，并说明恢复原安装流程所需条件。
- 只更新当前安装，不创建第二套 CLI。官方 GitHub 源码安装可迁移到 PyPI 稳定版。版本相同或本地版本更高时跳过包重装，同时修复已有 Skill 的同步状态。
- 自动发现已有默认 Skill 和登记过的自定义路径；不会新建未选择的 Agent 安装。本地修改及目录冲突会阻止更新，需先备份并移走冲突文件。未变化文件不重复复制。
- 更新在包外部的临时辅助进程中进行；POSIX 替换原 CLI 进程，Windows 等待原 Python 进程及 `.exe` 启动器退出后更新。Windows 首次返回 `state: started, completed: false`，**不代表更新成功**；按输出路径查看 `result.json` 的 `ok: true`，失败详情见同目录日志。可再次执行 `yicloud --version` 和 `yicloud skill status` 核对。
- 包安装、CLI 入口、版本和 Skill 校验全部成功后才报告完成。失败可能已改变部分 Python 包，安装器不承诺回滚；使用报告中的原环境命令修复，不要另装一套 CLI。中断后残留锁仅在确认无更新进程运行后手动移除。

`skill status` 是离线检查：`matching` 表示与本地内置 Skill 一致，`remote_checked: false`。远端版本请使用 `update --check`。卸载 Skill 时仅移除受管理且哈希未变的文件：

```sh
yicloud skill uninstall --target codex
```

更新不删除或重写账号、认证和 context 配置；自定义 Skill 路径单独存储在账号配置文件旁的 `config.json.skills.json`（文件名随 `YICLOUD_CONFIG` 改变），不含凭据。失败诊断保存在用户私有临时目录，排查结束后可删除。

### 从 0.3.1 迁移

`0.3.1` 没有 `update` 命令。当前按上面的“当前源码安装的更新”执行一次原环境引导升级，再同步已有 Skill 即可；无需安装 uv 或迁移账号配置。

未来 `0.4.0` 正式发布后，也可将对应原管理器命令的 GitHub 来源换成 `yicloud-skill==0.4.0`，然后运行 `yicloud update` 同步已有默认 Skill。自定义目录先执行一次带原 `--path` 的 `skill install`，以登记后续自动同步路径。尚未发布的版本与 tag 不能作为安装来源。

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

Windows 使用 `.venv\Scripts\python.exe`。CI 覆盖 Python 3.10、3.11、3.12 与 Linux、macOS、Windows，检查 lint、测试、Skill、wheel/sdist 内容、隔离安装及真实管理器的离线更新交接。`tools/check_updater.py` 用受控版本 fixture 模拟旧安装，不是历史 `0.3.1` 二进制回放；所有写入均限制在临时目录，不需要真实云账号。

## Release Process

版本唯一来源是 `pyproject.toml`。修改版本后执行完整 CI，创建并推送匹配的 `vX.Y.Z` tag 才会触发发布。本次改造不创建 tag、不发布 Release 或 PyPI。

发布工作流复用跨平台 CI，构建并验证 tag、wheel、sdist，通过 PyPI Trusted Publishing 上传同一批产物；仅在 PyPI 成功后创建 GitHub Release 并附加产物，避免发布失败被呈现为完整发布。初次使用需配置 GitHub `pypi` environment 及 PyPI Trusted Publisher；详见 [RELEASING.md](RELEASING.md)。

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
- 更新需要可访问 PyPI 或官方 GitHub、原安装管理器及当前环境写权限；不使用 sudo，不安装缺失的管理器，不处理系统包管理器维护的 Python。
- Windows 更新异步完成；原生 Windows 行为应以该平台 CI/实测结果为准。开发分支的提交更新由原源码安装流程负责。

## License

[MIT](LICENSE)。项目设计参考 InspireSkill，详见[第三方声明](THIRD_PARTY.md)。
