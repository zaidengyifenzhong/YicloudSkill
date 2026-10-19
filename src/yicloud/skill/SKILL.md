---
name: yicloud
description: 通过 yicloud CLI 操作仪电智算云平台的开发机、训练、Ray、模型部署、存储和管理 API，支持标准 SSH 与任务观察闭环。
---

使用 `yicloud --help` 发现命令，子命令 `--help` 查询参数；复杂请求先运行 `yicloud api describe SERVICE ACTION`。API 字段区分大小写，`Id`、`ID`、`JobId` 不可互换。

Yicloud 的 Workspace 是开发机。交互调试选 `workspace`，批量训练选 `job`，Ray 分布式任务选 `ray`，持续模型服务选 `serving`。不要将其他平台的 Workspace、Notebook 或资源标识直接套用。

先核对 `yicloud account current`、`yicloud project list`、`yicloud resources zones`，再在明确项目和可用区内查询 SKU、配额组、镜像与资源。创建命令显式指定项目、可用区、镜像和规格；通用 API 请求使用 SDK 的真实字段。实时查询容量，配额不等于当前空闲节点。资源默认按 ID 定位，按显示名时使用 `--by-name`，同名候选不得自动选择第一项。

最短闭环：查询资源 → 准备共享路径和请求文件 → `create --dry-run` → 提交并保留 ID → `status` / `wait` → 查看日志、实例或事件 → 核验产物 → 按用户意图清理。写请求中断后结果可能未知，先查询远端状态，避免重复创建。中断本地等待不会停止远端任务。

只按当前任务读取：

- [accounts.md](references/accounts.md)：首次认证、多账号、错误和脱敏。
- [resources.md](references/resources.md)：项目、地域、可用区、SKU、配额与空闲节点。
- [workspace-ssh.md](references/workspace-ssh.md)：开发机生命周期、SSH/exec/scp 和训练实例连接。
- [jobs.md](references/jobs.md)：训练、多角色、训前检查、纳秒日志。
- [ray.md](references/ray.md)：Ray 任务、Worker、事件和历史日志。
- [serving.md](references/serving.md)：部署、扩缩容、实例和日志。
- [storage.md](references/storage.md)：云盘、文件存储、对象存储与 S3 衔接。
- [assets.md](references/assets.md)：镜像、模型与数据集版本。
- [services-sandbox.md](references/services-sandbox.md)：托管服务、沙盒与预热池。
- [admin.md](references/admin.md)：权限、管理、账单和监控。
- [workflows.md](references/workflows.md)：端到端操作、产物验收和可选 YICLOUD.md。
- [api.md](references/api.md)：通用调用、SDK 合同、生成器和已知差异。
- [support.md](references/support.md)：每个公开请求操作的支持状态。

当前依据 SDK v0.5.1 固定提交；普通 HTTP 能力仅经过离线模拟验证，尚无真实平台兼容性证据。网页终端、WebSocket 实时日志暂缓；自动刷新使用历史日志轮询。标准 SSH 需要先向平台登记公钥并取得实际网关连接命令；不要从 Pod IP 推测公网地址或拼接网关用户名。`--json` 不可与无限日志跟随或交互 SSH 混用。
