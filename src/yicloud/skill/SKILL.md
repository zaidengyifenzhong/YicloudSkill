---
name: yicloud
description: 使用 yicloud CLI 操作仪电智算云的开发机、训练、Ray、模型部署和存储，支持 SSH 与任务排错。
---

Yicloud 的 Workspace 是开发机：交互调试用 `workspace`，训练用 `job`，分布式作业用 `ray`，持续推理用 `serving`。

已知命令时直接执行；不确定参数时查该子命令的 `--help`。只有准备复杂请求时才用 `api describe SERVICE ACTION`；字段大小写以输出为准。查询接口目录时限定 `api list --service SERVICE`，不要为单个任务加载全部目录或支持矩阵。

沿用已明确的账号、项目、可用区和资源 ID。首次配置或切换环境读 [账号](references/accounts.md)；选择新资源读 [资源](references/resources.md)。查询已有任务或使用已登记 SSH 连接，无需重新发现所有资源。显示名使用 `--by-name`，同名不可任选；Ray 操作标识是 JobName。

按任务读取对应参考，已有信息足够时无需重复读取：

- 开发机、SSH、exec、文件传输：[workspace-ssh.md](references/workspace-ssh.md)。
- 训练与日志：[jobs.md](references/jobs.md)；Ray：[ray.md](references/ray.md)；模型部署：[serving.md](references/serving.md)。
- 数据与挂载：[storage.md](references/storage.md)；镜像、模型、数据集：[assets.md](references/assets.md)。
- 托管服务与沙盒：[services-sandbox.md](references/services-sandbox.md)；权限、配额管理与账单：[admin.md](references/admin.md)。
- 跨开发、训练、部署的连续任务或维护项目资产：[workflows.md](references/workflows.md)。
- 便利命令未覆盖的 API、响应与错误处理：[api.md](references/api.md)。

创建前明确资源规格与输入输出路径，复制所需的 `assets/examples/` 模板到用户项目并替换占位符，dry-run 后提交。记录返回标识，观察状态与日志，按用户目标验收产物。写请求超时或中断后先查询远端状态，避免重复创建；中断本地等待不会停止远端任务。清理遵循用户的资源保留意图。
