# Changelog

## Unreleased

- 为现有 225 个 HTTP 操作补齐专用命令入口，保留既有命令；新增数据集、模型仓库、存储、IAM、账单、沙盒等命令组。`api list/describe` 新增 `command` 字段，未实现的协议接口为 null。
- 新增 `job edit RESOURCE`、`workspace edit RESOURCE`、`serving update RESOURCE`，提供类型化字段参数、JSON 对象/数组、请求文件及 dry-run；编辑操作使用资源 ID，不解析显示名。
- 新增命令仅补齐缺失的 Project/ZoneId 上下文，不覆盖显式值；完整请求文件不注入字段，且与字段参数、资源位置参数互斥。布尔参数显式传 true/false，保留 false、0、空数组和 null。
- 新增批量训练删除 `job batch-delete`，分页查询的 `--all` 与下载接口的 `--output`。通用 API、旧命令参数及认证/配置格式保持兼容；未新增 WebSocket 协议支持。
- 修复文件目录 `Files` 响应的分页读取；服务端限制每页条数时按 Total 和实际 Offset 继续查询，检测重复页与未到总数就返回空页的异常。
- 修复日志跟随在空响应后提前推进时间起点的问题，避免跳过尚未进入日志索引的旧时间戳事件。
- CPU Job 快捷配额模式缺省 GPU 显式为 "0"，保持请求文件、通用 API、SKU 与 Workspace 的原始字段语义。
- Job 快捷创建支持显式资源模式、QoS、优先级和任务等待/运行时限；省略时保留平台默认行为，不改写文件请求。
- 已知创建失败提供可选 error.hints，保留原平台错误和请求，不自动重试或改写重试策略；枚举错误说明固定 SDK 校验依据。
- 完成单副本 CPU Job 文件模式真实闭环：创建、运行、日志、GPFS 跨任务产物哈希校验、停止及删除确认；问题文档记录失败尝试、修复、平台差异和未验证范围。

## 0.2.1

- 开发机 SSH、exec、SCP、ssh-config 和 doctor 支持自动解析平台 ID 或名称，已有登记优先。共享连接显式指定登录用户名，自定义部署可指定网关。
- 自动连接默认开启 Agent 转发，支持单次关闭；不自动保存连接或开启 X11。
- 增加 GPU 离线环境、CPU 镜像准备及内部包源指引。
- Skill 补齐标准 SSH Host、持续 shell 会话和 GPU 路径诊断；明确全局参数位置及项目文件查找范围。

## 0.2.0

- 修复极端日期溢出和损坏 SSH 配置的类型校验，保持 JSON 错误契约。
- Job 快捷命令改用 `sh -c`；依赖登录初始化的调用须加 `--login-shell`。请求文件 Command 不变。
- 新增命名 context 管理及 --context/--no-context；便利命令补齐范围，显式参数优先，通用 API 和请求文件不注入字段。
- 新增 skill status 内容一致性检查、connection list/show/remove、本地/API/SSH 只读 doctor。
- SCP 新增 --recursive；logs 支持 --since 和带时区 RFC3339，精确保留纳秒。
- wait 新增 --no-timeout，区分 wait_timeout、remote_failed、unknown_state 并附最后观察证据。
- 保留普通 token 计数和 tokenizer 输出，继续遮盖凭据与已知秘密；JSON meta 附实际操作上下文。
- Skill 以平台操作为界，优先复用用户资源，移除固定训练部署流程与个人资源台账。

- 工作负载按名操作新增 `--lookup-set FIELD=JSON`，独立传递 Creator/Self/CreatorId/Scope 等列表过滤，保留跨页查找与同名拒绝。
- 修正 Skill 的资源池容量示例，补充 SKU 范围、配额组用途、个人列表分页及实测 SSH/云盘语义边界。

- CLI 帮助仅显示当前操作支持的参数；过去被忽略的无关参数现在会报错。Ray 和 serving 创建仅接受请求文件，workspace 不再展示训练命令参数。
- 查询命令仅提供 API 支持的项目、可用区和分页选项。复杂请求仍可使用 `api call`。
- 显式项目或可用区与 `--set` 重复指定时直接报错；工作负载的 `--file` 与 `--set` 也不能重复定义同一字段。
- 普通模式显示可读错误；`--json` 保留结构化失败信封。
- `api describe` 仅输出当前请求需要的类型定义。
- 请求模板随 Skill 安装，源码位置由 `examples/` 调整为 `src/yicloud/skill/assets/examples/`。
- Skill 按任务加载资料，公共文档聚焦使用、架构与贡献流程。

Python 公共入口、账号与 SSH 配置格式保持兼容。保留命令使用相同的平台请求语义；以下 CLI 调用需要迁移：

- `ray workers --set WorkerGroups=...` 改为 `--file workers.json`，文件内容为 `{"WorkerGroups": [...]}`。
- 日志请求中的时间、条数与实例过滤使用 `--start/--end/--limit/--instance`；不能再由附加 JSON 重复指定，Direction 由日志模式管理。需要原始字段组合时用 `api call`。
- 无额外业务字段的操作不再接受 `--file/--set`；移除过去未生效的附加参数。

按 ID 的 dry-run 不联网；按名称的 dry-run 可能执行只读查找，不提交平台写操作。
