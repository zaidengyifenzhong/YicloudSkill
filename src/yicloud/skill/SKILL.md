---
name: yicloud
description: 使用 yicloud CLI 操作仪电智算云的开发机、训练、Ray、模型部署和存储，支持 SSH 与任务排错。
---

Yicloud 的 Workspace 是开发机。`workspace` 适合交互开发，`job` 提供托管任务生命周期，`ray` 提供 Ray 作业，`serving` 提供模型服务。按用户所需的连接、调度和生命周期选择；允许在开发机调试训练或使用用户自己的启动器，不替用户决定研究框架、代码结构或实验方法。

已知命令时直接执行；不确定参数时查该子命令的 `--help`。只有准备复杂请求时才用 `api describe SERVICE ACTION`；字段大小写以输出为准。查询接口目录时限定 `api list --service SERVICE`，其 command 字段给出专用入口，不要为单个任务加载全部目录或支持矩阵。新增字段命令的布尔值传 true/false，对象和数组传 JSON；具体约定见 [API](references/api.md)。

`--json`、`--account`、`--context` 等全局选项放在子命令之前，例如 `yicloud --json context show`。参数解析失败不代表认证或网络失败。

沿用用户指定的机器、连接、账号、项目、可用区和资源 ID；仅在需要新资源时进入创建流程。可用命名 context 复用账号、项目和可用区，显式参数优先；`context show` 查看来源，`--no-context` 忽略默认上下文。请求文件和通用 API 字段不会被自动补齐。首次配置或切换环境读 [账号](references/accounts.md)；选择新资源读 [资源](references/resources.md)。查询已有任务或使用已登记 SSH 连接，无需重新发现所有资源。显示名使用 `--by-name`，同名不可任选；Ray 操作标识是 JobName。

连接来源同时包括 CLI 登记与标准 OpenSSH Host；未登记不等于没有连接。连续在同一机器操作时复用已确认目标的 SSH 终端会话，独立查询使用一次性 exec，详见 SSH 参考。平台查询优先 CLI；缺少连接信息不自动转浏览器，仅在用户已明确授权控制台操作时使用。

YICLOUD.md 只在当前步骤需要项目资产或包源时读取。优先已有账号、context 和连接信息；文件读取、搜索限于当前项目或用户明确给出的路径，找不到不扩展到主目录。检查已知的 `~/.ssh/config` 不需要全盘搜索；不读取私钥内容。

按任务读取对应参考，已有信息足够时无需重复读取：

- 安装版本、只读诊断和上下文：[developer-tools.md](references/developer-tools.md)。
- 开发机、SSH、持续会话、文件传输及 GPU 环境排错：[workspace-ssh.md](references/workspace-ssh.md)。
- 训练与日志：[jobs.md](references/jobs.md)；Ray：[ray.md](references/ray.md)；模型部署：[serving.md](references/serving.md)。
- 数据与挂载：[storage.md](references/storage.md)；镜像、模型、数据集：[assets.md](references/assets.md)。
- CPU 联网准备、GPU 离线环境与内部源：[internal-sources.md](references/internal-sources.md)。具体包源地址按需读取用户项目的 YICLOUD.md，不写入公开 Skill。
- 托管服务与沙盒：[services-sandbox.md](references/services-sandbox.md)；权限、配额管理与账单：[admin.md](references/admin.md)。
- 跨开发、训练、部署的连续任务或维护项目资产：[workflows.md](references/workflows.md)。
- 专用命令入口、通用 API、响应与错误处理：[api.md](references/api.md)。

创建前明确资源规格与输入输出路径。H200 默认不连外网；公网内容在可联网 CPU 开发机准备，内部源覆盖的依赖可在目标 GPU 环境安装验证，再固化镜像，见[离线环境与内部源](references/internal-sources.md)。简单请求使用快捷参数，复杂请求按需复制 `assets/examples/` 模板并替换占位符，dry-run 后提交。记录返回标识，观察状态与日志，按用户目标验收产物。写请求超时或中断后先查询远端状态，避免重复创建；中断本地等待不会停止远端任务。清理遵循用户的资源保留意图。

dry-run 只验证固定 SDK 请求结构，不能替代服务端业务校验。平台拒绝后保留错误码和 request_id，结合可选 hints 与实时资料定位；不连续猜测参数、不静默改写用户的重试策略。真实联测用独立临时任务及目录，分别核验日志、真实产物和最终清理状态；CPU Job 的验证范围、调度选项及已知策略差异见 [jobs.md](references/jobs.md)。
