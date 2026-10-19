# YicloudSkill

让 Codex、Claude Code 等 Agent 通过可复现命令管理仪电智算云。项目包含同一安装包中的 **yicloud CLI、同步 Python 客户端与按任务组织的 Skill**。

首版基于官方 Go SDK **v0.5.1**，固定提交 `8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5`，文档核对于 **2026-10-19**。227 个公开请求操作全部进入目录，225 个普通 HTTP 操作可调用，网页终端和 WebSocket 日志尾随 2 项明确暂缓。**已在 Apple Silicon Mac 上验证 `.com.cn` 环境的 HMAC 认证和部分只读 API，以及真实开发机的 SSH、远程执行、标准输入、退出码和 SFTP 往返。创建、启停、删除等平台写操作、Token 和服务账号认证尚未联机验证。**

## 安装

需要 Python 3.10+。运行时无需 Go。推荐 uv，也支持 pipx。安装脚本从 GitHub 安装 CLI，然后安装包内匹配的 Skill；不依赖 PyPI 发布。

macOS / Linux：

```bash
bash install.sh                       # 仓库内运行，默认安装到 Codex 和 Claude Code
bash install.sh --target codex
bash install.sh --manager pipx --target claude
```

Windows PowerShell：

```powershell
.\install.ps1 -Target all
.\install.ps1 -Manager pipx -Target claude
```

也可直接安装：

```bash
uv tool install --python 3.12 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
yicloud skill install --target all
# 或 pipx install 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main'
```

若 shell 暂时找不到 yicloud，用 `uv tool run --from 'git+https://github.com/zaidengyifenzhong/YicloudSkill.git@main' yicloud --help` 检查，并按工具管理器提示将其 bin 目录加入 PATH。安装器不修改 shell 配置、不设置更新任务。

Codex 默认安装到 `${CODEX_HOME:-~/.codex}/skills/yicloud`，Claude Code 到 `~/.claude/skills/yicloud`。自定义路径：

```bash
yicloud skill install --target codex --path ./agent-skills/yicloud
yicloud skill uninstall --target all
uv tool uninstall yicloud-skill
# pipx uninstall yicloud-skill
```

同名非本项目 Skill 拒绝覆盖。升级保留额外用户文件，已有管理文件被手动修改时停止覆盖；卸载仅移除内容未改变的包内文件和管理标记。账号、SSH 连接、YICLOUD.md 默认保留。升级 CLI 后再运行 skill install 同步资料。

## 首次使用

```bash
yicloud account add research --auth hmac
yicloud account use research
yicloud account check
yicloud project list
yicloud resources zones
yicloud resources skus --project example-project --zone example-zone --set 'SKUType="gpu"'
yicloud resources quota-groups --project example-project --zone example-zone
```

私钥/Token 通过隐藏交互输入。账号默认存储在 `~/.config/yicloud/config.json`，POSIX 限制为 0600；可通过 YICLOUD_CONFIG 指定文件。地址、地域为命令参数 → 环境变量 → 账号 → 官方默认值。官方认证变量整体覆盖，避免混合两个账号的公私钥；Token 优先，认证失败不切换身份。详见[认证说明](src/yicloud/skill/references/accounts.md)。

控制台 `console.yicloud.com` 对应默认 API `https://gate.yicloud.com`；`console.yicloud.com.cn` 则对应 `https://gate.yicloud.com.cn`。两套环境使用各自的凭据。使用后者时，创建账号需增加 `--host https://gate.yicloud.com.cn`，也可用全局 `--host` 临时验证。[官方域名说明](https://docs.yicloud.com/8/1.html)。

所有 example-*、EXAMPLE_* 和 gateway.example 都是占位符，必须用当前账号的实时查询结果替换。Yicloud Workspace 表示开发机；项目、地域、可用区、SKU 和配额组保持平台自身语义。

## 通用 API

```bash
yicloud api list --service job
yicloud api describe job CreateJob
yicloud --account research api call job CreateJob --file examples/job.json --dry-run
yicloud --account research --json api call job CreateJob --file examples/job.json
```

目录包含存储、镜像、模型、数据集、服务托管、沙盒、管理、权限、监控和账单，管理员写操作也可调用，权限由平台执行。`--file -` 支持 stdin；无字段请求可省略文件。JSON 字段大小写必须符合官方合同；默认拒绝未知字段，明确需要服务端新增字段时用 --allow-unknown-fields。dry-run 不发送请求、不展示凭据和签名，不代表平台权限或业务条件已满足。

`--json` 成功输出：

```json
{"ok":true,"data":{},"meta":{"service":"job","action":"ListJobs","request_id":"..."}}
```

业务、输入等错误在 stderr 输出 `{"ok":false,"error":{"kind":"...","message":"...","code":null,"request_id":null,"outcome_unknown":false,"http_status":null}}` 并返回非零。本地 Ctrl-C/交互取消返回 130；`--json` 使用同一失败信封，kind 为 interrupted，并保守标记结果未知，普通模式输出文字说明。中断不能证明远端写操作未发生。HTTP 错误保留脱敏后的平台 Msg、有效整数业务 Code、HTTP 状态与请求 ID，便于诊断环境或凭据不匹配；畸形的成功响应业务码按协议错误处理，写结果未知。默认脱敏；显式全局 --show-secrets 才显示新返回的秘密字段。HTTP 请求默认超时 30 秒，只读最多两次附加重试；写请求不自动重试，超时或中断后应先查询远端状态。正常 TLS 校验，不自动跟随重定向。

## 常用算力工作流

```bash
yicloud job create --file examples/job.json --dry-run
yicloud job create --file examples/job.json
yicloud job status JOB_ID --project example-project --zone example-zone
yicloud job replicas JOB_ID --project example-project --zone example-zone
yicloud job logs JOB_ID --project example-project --zone example-zone --follow
yicloud job wait JOB_ID --project example-project --zone example-zone --timeout 1800
```

workspace/job 另有常用参数创建模式：

```bash
yicloud job create --name train --project example-project --zone example-zone \
  --image example/image:tag --command 'python /mnt/project/train.py' \
  --sku EXAMPLE_SKU --sku-scope public --dry-run
yicloud workspace create --name devbox --project example-project --zone example-zone \
  --image example/image:tag --quota-group example-quota --cpu 4 --memory 16Gi --dry-run
```

开发机快捷创建使用 50Gi 系统盘；自定义规格用文件。创建文件与快捷参数互斥。复杂训练角色、Ray Worker 和部署拓扑用 JSON。ID 直接定位，按显示名使用 --by-name 并限定项目/可用区；同名报告候选。列表默认 20 条，--all 读取有分页合同的全部页。配额不等于当前空闲资源。

workspace 提供 start/stop/restart/delete/processes；job 提供 stop/delete/precheck/replicas；ray 提供 stop/delete/events/instances/workers；serving 提供 start/stop/delete/scale/instances。没有训练/Ray start 接口就不提供该命令。`wait` 每 5 秒查询、默认 30 分钟，未知状态报错；Ctrl-C 只停止本地等待。日志默认最近 10 分钟、200 条，--start/--end 使用纳秒时间戳，跟随每 3 秒轮询并减少重复。繁忙窗口可被条数上限截断，不能把轮询当作可靠日志归档。

## 标准 SSH

先在平台登记 SSH 公钥并从开发机详情取得实际网关命令，再保存连接：

```bash
yicloud workspace connection set devbox --project example-project --zone example-zone \
  --ssh-command 'ssh -p 2202 user@gateway.example' --identity ~/.ssh/id_ed25519
yicloud workspace ssh devbox --project example-project --zone example-zone
yicloud workspace exec devbox --project example-project --zone example-zone -- nvidia-smi
yicloud workspace scp ./train.py devbox:/mnt/project/train.py --project example-project --zone example-zone
yicloud workspace ssh-config devbox --project example-project --zone example-zone
```

支持 Host 别名和 ProxyJump，保留完整用户名和主机密钥校验。导入命令只解析支持的参数，不执行原始字符串。exec 继承 stdin 并传递远端退出码；scp 使用现代 OpenSSH 默认 SFTP（建议 OpenSSH 9+）。ssh-config 输出片段，不修改 ~/.ssh/config。训练实例启用 SSH 并登记连接后也支持 job ssh/exec/scp/ssh-config。JSON 不可与 SSH 或无限日志跟随混用。参见[开发机与 SSH](src/yicloud/skill/references/workspace-ssh.md)。

2026-10-19 Mac 实机验证：macOS 26.7.1 / arm64、OpenSSH 10.3，使用登记的本机密钥连接真实开发机；CLI 接受平台复制的 `ssh -CAXY ... -p 2202`，验证 UTF-8 标准输入、远端退出码 23、含空格路径的 SFTP 上传下载，文件 SHA-256 一致，远端临时文件已清理。此记录不代表所有镜像、网关或 HTTP API 已验证。

同日完成 `.com.cn` 环境 HMAC 认证、项目/可用区/配额/GPU SKU 查询、开发机详情及训练/Ray/部署列表的只读调用。部署列表实际使用内层 `Data` 数组，便利命令已兼容。独立对照确认：相同环境及标量参数下，固定 Go SDK 与 Python 均出现开发机列表为空、按已知 ID 查询详情成功；服务端原因尚未确定，空列表不能作为资源不存在的证据。未执行平台写操作。完整范围见 [API 说明](src/yicloud/skill/references/api.md)。

部分容器镜像的登录初始化脚本可能无法由 `sh` 解析。本次镜像的 `sh -lc` 在 `/etc/profile.d/ssh-init.sh` 报语法错误，直接执行命令和 `sh -c` 正常；应将镜像脚本错误与 SSH 连接错误区分，不要自动修改用户镜像。

## Python 客户端

```python
from yicloud import YicloudClient

with YicloudClient.from_account("research") as client:
    result = client.call(
        service="job",
        action="ListJobs",
        params={"Project": "example-project", "ZoneId": "example-zone", "Limit": 20},
    )
    print(result.data, result.request_id)
    # result.raw 为 httpx.Response；原始响应可能含秘密，脚本需自行处理。
```

同步客户端支持上下文管理、MockTransport 注入、自定义 timeout、dry_run、文件输出及分类异常。便捷命令和通用 API 使用相同客户端。首版无异步客户端。

## 能力、来源与限制

| 范围 | 支持 |
|---|---|
| SDK 全部公开请求操作 | 227 项收录，逐项见[支持矩阵](src/yicloud/skill/references/support.md) |
| 普通 HTTP / 管理员写操作 | 225 项，含直接文件存储响应和日志下载 |
| workspace / job / ray / inferset | 生命周期、资源定位、等待、日志与实例等便利命令 |
| 标准 SSH | 已通过 Mac 实机连接、exec 和 SFTP 验证，需用户提供实际网关连接信息 |
| 对象存储 | bucket 管理；对象传输另接官方 S3 工具工作流 |
| WebSocket 尾随 / 网页终端 | 2 项暂缓，明确报错；日志自动刷新用轮询 |
| 真实平台兼容性 | SSH、HMAC 及部分只读 API 已实测；平台写操作未联测，自动测试使用合成数据 |

官方 [文档](https://docs.yicloud.com/) 说明流程，[固定 Go SDK](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5) 定义合同。fs/alpha 实际使用 yifs 路径且存在函数名/路径差异；标量数组编码为重复查询键以避免 SDK 丢项；Ray 历史日志保留直接 JSON；部署下载按文件处理。差异和维护方法见 [API 说明](src/yicloud/skill/references/api.md)。

设计参考 [InspireSkill](https://github.com/realZillionX/InspireSkill) 的 CLI + Skill 分层、按需参考和稳定资产文档模式，未复制其平台私有 API 或账户资产。归属见 [THIRD_PARTY.md](THIRD_PARTY.md)。

## 开发与验证

后续 Agent 的角色分工、任务依赖、联机验证与发布流程见 [Agent 交付流程](docs/agent-workflow.md)，可交接的任务清单见 [agent-tasks.yaml](docs/agent-tasks.yaml)。流程从当前已实现版本继续，区分首版交付与额外真实工作流验证。

[架构设计](docs/architecture.md)说明 CLI 命令组、工作负载规则、公共客户端、平台协议与 HTTP 传输的依赖边界，以及本次重构的兼容性约束。[独立执行记录](docs/refactor-review.md)列出各角色实际发现、修复、验收证据和保留限制。

```bash
uv venv --python 3.12
uv pip install -e '.[dev]'
python -m pytest
ruff check src tests tools
ruff format --check src tests tools
python tools/check_catalog.py
python tools/validate_skill.py
python -m build
python tools/verify_wheel.py dist/yicloud_skill-0.1.0-py3-none-any.whl
```

测试默认完全离线。CI 在 Linux、macOS、Windows 上执行测试、静态检查、构建与独立虚拟环境 wheel 安装；另有固定 SDK 目录再生成及 Go 签名向量对照。维护工具需要 Go 标准库，用户安装不需要。每次发布将 CLI 与 Skill 一起打包；wheel 验证从仓库之外运行，不允许依赖本地源文件。尚未发布 PyPI 或 GitHub Release。

Skill 入口位于 [src/yicloud/skill/SKILL.md](src/yicloud/skill/SKILL.md)，安装器复制完整版本。可选 YICLOUD.md 用于用户项目稳定资产，不保存凭据、实时配额和运行状态。
