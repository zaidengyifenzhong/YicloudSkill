# YicloudSkill

让 Codex、Claude Code 使用仪电智算云：查询算力、管理开发机、提交训练任务、部署模型，以及通过 SSH 执行命令和传输文件。

项目将 Agent Skill、`yicloud` CLI 和 Python 客户端一起发布。Skill 提供平台操作指引，CLI 提供可复用的命令，也可以独立使用。

## 安装

需要 Python 3.10+、Git 和 [uv](https://docs.astral.sh/uv/)。

```bash
uv tool install --python 3.12 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
yicloud skill install --target all
```

`--target` 可选 `codex`、`claude` 或 `all`，默认安装到对应 Agent 的用户 Skill 目录。安装后若找不到 `yicloud`，请按 uv 的提示将工具目录加入 PATH。

也支持 pipx；克隆仓库后可使用 `bash install.sh`（macOS / Linux）或 `.\install.ps1`（Windows）完成安装。

从源码更新可运行 `uv tool install --force .`，然后运行 `yicloud skill install --target all` 同步指引和模板。`yicloud skill status` 可检查安装内容是否一致；安装器会保留本地修改并报告冲突。

## 快速开始

添加本地凭据配置，按提示输入已有云平台账号的凭据；`account add` 不会创建云平台账号：

```bash
yicloud account add research --auth hmac --host https://gate.yicloud.com.cn
yicloud account use research
yicloud account check
```

`research` 是自定义的本地配置别名，可以改为 `work` 等名称；后续 `account use`、`--account` 和 Python 的 `from_account()` 使用同一别名。它与平台用户名（例如查询开发机时的 `Creator`）及项目标识 `Project` 是不同的概念，不能相互替代。

网关应与控制台一致：`console.yicloud.com.cn` 使用 `gate.yicloud.com.cn`，`console.yicloud.com` 使用 `gate.yicloud.com`。多账号、Token 和环境变量配置见[认证说明](src/yicloud/skill/references/accounts.md)。

然后向 Agent 描述任务。在 Codex 中可以显式调用 `$yicloud`：

> 使用 $yicloud，查看我的项目、可用区和可用 GPU 规格。

> 使用 $yicloud，为当前项目准备一个单卡训练任务，检查数据和输出路径，先执行 dry-run。

> 使用 $yicloud，检查任务 JOB_ID 的状态和最近日志，帮我定位失败原因。

## 命令行

查询资源：

```bash
yicloud project list
yicloud resources zones
yicloud workspace list --project PROJECT --zone ZONE
```

提交训练并查看日志：

```bash
yicloud job create --file job.json --dry-run
yicloud job create --file job.json
yicloud job logs JOB_ID --project PROJECT --zone ZONE --follow
```

`PROJECT`、`ZONE` 和 `JOB_ID` 需替换为实际值。`job.json` 可从仓库中的[请求示例](src/yicloud/skill/assets/examples)复制并修改；`dry-run` 仅校验本地请求，不提交任务。

已实现的 225 个 HTTP 操作均有专用命令入口。常用工作流使用 `job create`、`workspace stop` 等简短命令；其他操作通常按 API 名称转为短横线形式，例如 `volume create-volume`、`dataset list-data-sets`。`inferset` 接口放在 `serving` 下，旧版文件存储放在 `fs alpha` 下。通过 `api list --service SERVICE` 的 `command` 字段可查准确入口，具体参数用子命令 `--help` 查看。

```bash
# 修改训练优先级（Job 编辑接口不用于修改训练启动命令）
yicloud job edit JOB_ID --project PROJECT --operation priority --priority 5 --dry-run

# 修改开发机名称；显式布尔值可以传 false
yicloud workspace edit WORKSPACE_ID --project PROJECT --zone ZONE \
  --name new-name --internet false --dry-run

# 更新推理服务，数组与对象参数使用 JSON
yicloud serving update INFERSET_ID --project PROJECT \
  --image example/image:tag --command '["python", "serve.py"]' --dry-run

yicloud dataset list-data-sets --project PROJECT --all
yicloud volume create-volume --help
yicloud registry list-public-images --help
```

新增命令支持 `--file` 完整请求或字段参数，两者互斥。布尔参数传 `true/false`；对象和数组传 JSON；需要显式 null 时可用 `--set 'Description=null'`。`job edit`、`workspace edit`、`serving update` 的位置参数为资源 ID，不是显示名称。请求文件模式不与位置参数混用，文件中填写完整 ID 和范围。旧命令的参数约定保持不变。

复杂请求可先用 `api describe` 查询嵌套字段，再通过专用命令的 `--file` 或通用 API 调用：

```bash
yicloud api describe job CreateJob
yicloud api call job CreateJob --file job.json --dry-run
```

## 开发者工具

可选上下文减少重复范围参数，显式命令参数优先；通用 API 与请求文件保持原样：

```bash
yicloud context set lab --account research --project PROJECT --zone ZONE
yicloud context use lab
yicloud context show
yicloud job logs JOB_ID --since 15m
yicloud job wait JOB_ID --no-timeout
yicloud workspace connection list
yicloud workspace scp ./src devbox:/work/src --recursive
yicloud doctor local
yicloud doctor api
yicloud workspace doctor devbox
yicloud skill status --target all
```

`devbox` 可为已登记的连接或开发机名称；未登记时自动查询并生成 SSH 连接，名称查找可加 `--lookup-set 'Creator="PLATFORM_USER"'`，也可直接传 WorkspaceId。首次需向平台登记公钥。自动连接默认开启 Agent 转发，可用 `--no-forward-agent` 关闭；详见[SSH 指引](src/yicloud/skill/references/workspace-ssh.md)。

`--no-context` 忽略当前上下文；没有项目目录自动发现。0.2 的 job 快捷命令默认 `sh -c`，原先依赖登录初始化的调用加 `--login-shell`。请求文件的 Command 数组不变。等待超时不停止远端任务；目录复制不是增量同步。

上下文、诊断和输出契约见[开发工具](src/yicloud/skill/references/developer-tools.md)。远端长任务可使用 Job 或 Ray；SSH exec 为同步执行，SCP 为完整文件复制。

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
- [开发机与 SSH](src/yicloud/skill/references/workspace-ssh.md)
- [训练任务](src/yicloud/skill/references/jobs.md) · [Ray](src/yicloud/skill/references/ray.md) · [模型部署](src/yicloud/skill/references/serving.md)
- [存储](src/yicloud/skill/references/storage.md) · [镜像、模型与数据集](src/yicloud/skill/references/assets.md)
- [端到端工作流](src/yicloud/skill/references/workflows.md)
- [API 说明](src/yicloud/skill/references/api.md) · [接口支持矩阵](src/yicloud/skill/references/support.md)

当前基于仪电智算云 Go SDK v0.5.1，实现固定目录中的 225 个 HTTP 操作；该数量不等于线上控制台的全部路由。网页终端与 WebSocket 日志暂不支持，日志跟随使用轮询。已实测 `.com.cn` 的 HMAC、部分只读接口和 Mac 上的 SSH/SFTP；临时 CPU 开发机的创建、等待、删除，以及单副本 CPU Job 的创建、运行、日志、跨任务 GPFS 产物校验、停止和删除已实测。GPU/多副本 Job、Ray/Serving 写操作、Token 与服务账号认证尚未联机验证。接口行为与验证范围见 [API 说明](src/yicloud/skill/references/api.md)。

## License

[MIT](LICENSE)。设计参考 InspireSkill，详见[第三方声明](THIRD_PARTY.md)。
