# 开发机管理

## 何时读取

启动、停止、重启或删除开发机时读取。创建见[创建开发机](create.md)，清单和状态见[查询已有资源](../query.md)；仅需连接现有机器时转到[连接手册](connect.md)。

## 查询和定位

按[查询手册](../query.md)确定范围并定位唯一目标；已有 WorkspaceId 可省去名称解析，操作仍使用已确认的项目和可用区。不要用本地 SSH 登记冒充平台列表。

## 启停、重启和删除

先读取目标状态和依赖。使用对应 `start`、`stop`、`restart`、`delete` 子命令，先 dry-run 再执行。

- 停止后用 `workspace wait "$workspace_id" --target stopped` 验证最终状态。
- 删除前查询 `api describe workspace DeleteWorkspace`，确定关联云盘处理意图。附加删除字段通过 `--extra-file` 或命令支持的 `--set` 提供。
- 删除后用 `workspace wait "$workspace_id" --target deleted`，另按[存储手册](../storage.md)核对云盘结果。资源查询不再可见不等于磁盘物理销毁。

## 异常与完成标准

创建超时先按原名称和范围查询，避免重复机器；重名需要消歧。Running 只证明平台状态，不证明 SSH 或 GPU 环境正常。等待超时不停止机器；用户只要求停止时不删除。报告资源标识、操作后的状态，以及实际验证到的连接和环境能力。
