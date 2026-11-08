# 开发机创建与管理

## 何时读取

创建、启动、停止、重启或删除开发机时读取。清单和状态查询见[查询已有资源](../query.md)；仅需连接现有机器时转到[连接手册](connect.md)。

## 查询和定位

按[查询手册](../query.md)确定范围并定位唯一目标；已有 WorkspaceId 可省去名称解析，操作仍使用已确认的项目和可用区。不要用本地 SSH 登记冒充平台列表。

## 创建

1. 收集名称、镜像、资源模式与规格、磁盘和挂载要求。已有机器满足任务时复用，不自动创建。
2. 简单请求使用 `workspace create --help` 中的快捷参数；快捷创建包含 50Gi 系统盘。自定义磁盘、多挂载等使用 `api describe workspace CreateWorkspace` 构造完整请求文件，不提供猜测的默认挂载。
3. 执行 `workspace create --file "$request_file" --dry-run`，核对完整请求。通过且符合授权后移除 `--dry-run` 提交。
4. 保存返回 WorkspaceId，再执行 `workspace status "$workspace_id"` 和 `workspace wait "$workspace_id"`。需要开发环境可用时再按连接手册验证 SSH 和必要程序。

Workspace 创建请求没有 Command 字段；启动后的命令通过 exec 执行。不要套用训练 TaskSpecs。

## 启停、重启和删除

先读取目标状态和依赖。使用对应 `start`、`stop`、`restart`、`delete` 子命令，先 dry-run 再执行。

- 停止后用 `workspace wait "$workspace_id" --target stopped` 验证最终状态。
- 删除前查询 `api describe workspace DeleteWorkspace`，确定关联云盘处理意图。附加删除字段通过 `--extra-file` 或命令支持的 `--set` 提供。
- 删除后用 `workspace wait "$workspace_id" --target deleted`，另按[存储手册](../storage.md)核对云盘结果。资源查询不再可见不等于磁盘物理销毁。

## 异常与完成标准

创建超时先按原名称和范围查询，避免重复机器；重名需要消歧。Running 只证明平台状态，不证明 SSH 或 GPU 环境正常。等待超时不停止机器；用户只要求停止时不删除。报告资源标识、操作后的状态，以及实际验证到的连接和环境能力。
