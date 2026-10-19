# Changelog

## Unreleased

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
