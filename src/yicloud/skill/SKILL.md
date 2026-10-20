---
name: yicloud
description: 使用 yicloud CLI 查询和管理仪电智算云的开发机、训练、Ray、模型部署与存储，并完成 SSH 操作和任务排错。
---

# Yicloud 平台操作

根据用户目标选择能力：Workspace 用于交互开发，Job 用于托管训练，Ray 用于分布式作业，Serving 用于持续推理。沿用用户指定的机器、框架、账号和资源；查询或连接已有资源不进入创建流程。

## 按任务读取

只读取当前任务需要的手册。一个手册包含该任务的正常流程；出现异常或进入另一项任务时再加载相关文件。

| 任务 | 手册 |
|---|---|
| 配置账号、切换项目与可用区 | [访问与上下文](references/access.md) |
| 为新任务选择规格、配额或资源池 | [资源选择](references/resources.md) |
| 创建、查询或启停开发机 | [开发机管理](references/workspace/manage.md) |
| SSH、远程命令与文件复制 | [连接开发机和训练实例](references/workspace/connect.md) |
| SSH、GPU 或镜像初始化报错 | [远程环境排错](references/workspace/troubleshoot.md) |
| 提交或运行训练 | [训练执行](references/jobs/run.md) |
| 查询训练、日志、产物或清理 | [训练观察与结束](references/jobs/observe.md) |
| Ray 作业及 Worker 调整 | [Ray](references/ray.md) |
| 创建推理部署 | [部署创建](references/serving/create.md) |
| 查询、启动、停止或删除部署 | [部署管理](references/serving/manage.md) |
| 手动或自动扩缩容 | [扩缩容](references/serving/scaling.md) |
| 推理日志查询或下载 | [部署日志](references/serving/logs.md) |
| 挂载、传输或验证持久化产物 | [存储](references/storage.md) |
| 镜像、模型、数据集版本管理 | [资产](references/assets.md) |
| 容器应用托管 / 沙盒 | [应用](references/applications.md) / [沙盒](references/sandbox.md) |
| 权限、项目、配额管理 | [管理变更](references/administration.md) |
| 账单和指标查询 | [观测](references/observability.md) |
| 离线依赖、内部源与环境镜像 | [环境准备](references/environment.md) |
| 命令、安装或诊断异常 | [CLI 诊断](references/diagnostics/cli.md) |
| 复杂请求、通用 API 调用 | [API 操作](references/diagnostics/api.md) |
| 字段差异、未知响应、协议限制 | [兼容问题](references/diagnostics/compatibility.md) |

## 执行约定

- 已知命令直接使用；语法不确定时读取该命令的 `--help`。复杂请求查询 `api describe SERVICE ACTION`，它描述固定 SDK 的请求结构，不是实时服务端能力或响应合同。不要为单项任务加载全部接口目录。
- `--json`、`--account`、`--context` 等全局选项放在子命令前。优先从当前 context、用户输入、已核实资源或查询结果取得参数；只补问真正缺少的信息，不猜镜像、路径、规格或拓扑。
- 文中的 `$变量` 是调用形式说明：必须先取得真实值并赋值才执行；代码块不是待逐行执行的脚本。无需参数的命令直接使用。完整请求用 `--file`，生命周期附加字段用 `--extra-file`。
- 显示名称使用命令支持的 `--by-name`；把分页、名称消歧、字段转换交给 CLI。零匹配或多匹配时不写入。通用 API 不提供全部工作流保护，使用前阅读其手册。
- 对支持 dry-run 的 API 写入先校验请求。失败则修正有明确依据的格式或调用问题；通过不代表权限、容量、镜像和业务条件满足。名称解析可能先发起只读查询。
- 执行范围以当前用户授权为准，已有明确授权无需重复确认。改变规格、费用、访问范围、数据位置、运行策略或删除重建，必须属于当前授权；不能为了提交成功自行改变意图。
- 写入结果未知时先查实际状态，避免重复提交。同名资源需结合创建时间、配置和请求关联证据核对，不能冒认旧资源；暂时查不到也可能是可见延迟。等待超时或 Ctrl-C 不代表远端已停止。未知状态或未识别响应不能解释为成功或不存在。
- 验收深度由任务决定：提交成功、任务完成、产物可读、服务可调用分别取证。清理仅覆盖用户要求或本次创建且约定清理的内容。

项目资产与内部源按需读取当前项目或用户指定位置的 `YICLOUD.md`，不扩展搜索主目录。不写入凭据、临时访问 URL 或测试流水；保留可复用资源标识、路径和适用范围。
