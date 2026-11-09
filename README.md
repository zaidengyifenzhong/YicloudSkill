# YicloudSkill

让 Codex、Claude Code 使用仪电智算云：查询算力、管理开发机、提交训练任务、部署模型，以及通过 SSH 执行命令和传输文件。

项目包含 Agent Skill、`yicloud` CLI 和 Python 客户端。Skill 提供操作指引，CLI 和 Python 客户端也可单独使用。

## 安装

需要 Git、[uv](https://docs.astral.sh/uv/) 和 Python 3.10+；下面使用 Python 3.12。先安装 CLI，再安装它自带的 Skill：

```bash
uv tool install --python 3.12 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
yicloud skill install --target all
yicloud skill status --target all
```

`--target all` 同时安装到 Codex 和 Claude Code。只用其中一个时，把安装和更新命令中的 `all` 换成 `codex` 或 `claude`。

默认目录为 `~/.codex/skills/yicloud` 和 `~/.claude/skills/yicloud`；设置了 `CODEX_HOME` 时，Codex 使用该目录下的 `skills/yicloud`。找不到 `yicloud` 命令时，运行 `uv tool update-shell` 并重新打开终端。

也可克隆仓库后运行 `bash install.sh`（macOS / Linux）或 `.\install.ps1`（Windows）；脚本支持 uv 和 pipx。

## 更新 Skill

先从仓库 `main` 更新 CLI 及其自带的 Skill，再同步到 Agent 目录：

```bash
uv tool install --python 3.12 --force --upgrade 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
yicloud skill install --target all
yicloud skill status --target all
```

只更新 CLI、执行 `git pull` 或推送仓库，都不会自动更新 Agent 目录里的 Skill。`skill install` 可以重复运行，用于同步当前 CLI 自带的版本。

`skill status` 中目标的 `state` 为 `matching`，表示它与当前 CLI 自带的 Skill 一致，不代表已经检查过远端最新版。若安装器报告本地修改或同名目录冲突，先备份并移走提示的文件或目录，再重新安装；安装器不会直接覆盖这些内容。

## 快速开始

按提示配置已有云平台账号的凭据；`account add` 只添加本地配置，不创建平台账号：

```bash
yicloud account add research --auth hmac --host https://gate.yicloud.com.cn
yicloud account use research
yicloud account check
```

`research` 是本地配置别名，供 `account use`、`--account` 和 Python 的 `from_account()` 使用，不能代替平台用户名 `Creator` 或项目标识 `Project`。

网关应与控制台一致：`console.yicloud.com.cn` 使用 `gate.yicloud.com.cn`，`console.yicloud.com` 使用 `gate.yicloud.com`。多账号、Token 和环境变量见[认证说明](src/yicloud/skill/references/access.md)。

然后向 Agent 描述任务。在 Codex 中可以显式调用 `$yicloud`：

> 使用 $yicloud，查看我的项目、可用区和可用 GPU 规格。

> 使用 $yicloud，为当前项目准备一个单卡训练任务，检查数据和输出路径，先执行 dry-run。

## 命令行

查询资源：

```bash
yicloud project list
yicloud resources zones
```

提交训练并查看日志：

```bash
yicloud job create --file job.json --dry-run
yicloud job create --file job.json
yicloud job logs JOB_ID --project PROJECT --zone ZONE --follow
```

`PROJECT`、`ZONE` 和 `JOB_ID` 需替换为实际值。`job.json` 按下面的请求定义和真实资源配置准备；简单任务可用 `job create --help` 中的快捷参数。`dry-run` 只校验固定 SDK 请求结构，不验证权限、资源余量或运行结果。

查询请求定义、准确命令入口和参数：

```bash
yicloud api describe job CreateJob
yicloud api list --service job
yicloud job create --help
```

## 开发者工具

可用上下文保存账号、项目和可用区；显式命令参数优先。请求文件和通用 API 不自动补入项目、可用区字段：

```bash
yicloud context set lab --account research --project PROJECT --zone ZONE
yicloud context use lab
yicloud context show
yicloud doctor local
```

`--no-context` 忽略当前上下文，`context show` 可检查认证来源冲突。SSH 首次使用需在平台登记公钥；自动连接默认开启 Agent 转发，可用 `--no-forward-agent` 关闭。等待超时不停止远端任务，SCP 是完整复制。详见 [SSH 指引](src/yicloud/skill/references/workspace/connect.md)、[开发工具](src/yicloud/skill/references/diagnostics/cli.md)和[版本变更](CHANGELOG.md)。

## Python

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

## 文档

- [官方 OpenAPI 文档中心](https://api.yicloud.com.cn/)
- [完整任务导航](src/yicloud/skill/SKILL.md)：开发机、Job、镜像、存储、Ray 和模型部署
- [训练运行与产物](src/yicloud/skill/references/jobs/observe.md) · [存储](src/yicloud/skill/references/storage.md) · [镜像查询](src/yicloud/skill/references/images/query.md)
- [API 说明](src/yicloud/skill/references/diagnostics/api.md)：请求文件、通用调用与错误处理

接口目录固定于仪电智算云 Go SDK v0.5.1，不等于控制台的全部路由。网页终端与 WebSocket 日志暂不支持，日志跟随使用轮询。历史联测覆盖 `.com.cn` HMAC、部分查询、macOS SSH/SFTP、临时 CPU 开发机的创建/等待/删除，以及单副本 CPU Job 的创建、运行、日志、跨任务 GPFS 产物校验、停止和删除。GPU/多副本 Job、Ray/Serving 写操作、Token 与服务账号认证尚未联机验证。

## License

[MIT](LICENSE)。设计参考 InspireSkill，详见[第三方声明](THIRD_PARTY.md)。
