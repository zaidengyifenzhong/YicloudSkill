# 通用 API

已实现的 HTTP 操作均有专用入口，`api list` 与 `api describe` 的 `command` 字段给出对应命令；未实现协议的 command 为 null。通用 API 仍用于按官方字段调用和复杂请求。已知操作直接 describe；未知操作先限定服务查找：

```bash
yicloud api list --service job
yicloud api describe job CreateJob
yicloud api call job CreateJob --file job.json --dry-run
yicloud --json api call job CreateJob --file job.json
```

描述包含当前请求的 schema 及其引用类型。字段大小写、必填和枚举以描述为准；部分业务条件由服务端校验。`--file -` 从 stdin 读取 JSON 对象，无字段请求可省略文件。只有明确需要服务端新增字段时才用 `--allow-unknown-fields`，该选项不会绕过已有字段的枚举或类型校验。固定目录可能落后于线上平台：若实时返回的枚举值不被本地接受，先核对对应请求的正式合同；不要猜测其他值或静默修改生成目录。

专用入口保留既有工作流命令；新补齐的操作通常将 Action 转为短横线形式，如 `dataset list-data-sets`、`volume create-volume`。模型推理使用 `serving`，旧版文件存储使用 `fs alpha`。具体参数只查对应 `--help`。

新增命令的标量字段有类型化选项，`ZoneId` 使用 `--zone`，布尔值显式传 true/false；对象、数组使用 JSON。`--set FIELD=JSON` 支持补充字段和显式 null，不能与字段选项重复。完整 `--file` 与字段选项、`--set`、资源位置参数互斥；文件不注入上下文。不传文件时仅补齐未指定的 Project/ZoneId。分页 `--all` 只在支持 Limit/Offset 的只读操作上提供，与 dry-run 互斥；下载操作必须提供 `--output`（dry-run 除外）。API 的 All 字段使用 `--field-all`，与读取所有分页的 `--all` 区别开。

编辑命令使用资源 ID，不解析名称：

```bash
yicloud job edit JOB_ID --project PROJECT --operation priority --priority 5 --dry-run
yicloud workspace edit WORKSPACE_ID --project PROJECT --zone ZONE --name new-name --dry-run
yicloud serving update INFERSET_ID --project PROJECT --image example/image:tag --dry-run
yicloud job batch-delete --resources '[{"Project":"PROJECT","JobId":"JOB_ID"}]' --dry-run
```

Job 的 EditJob 仅提供优先级和置顶操作，不能据此修改镜像或启动命令。复杂编辑也可使用完整 `--file`，此时 ID 放在文件中。

通用 API 的 dry-run 校验并预览请求，不联网、不验证权限、不预留资源。便利命令的 `--by-name --dry-run` 会先进行只读名称查询。JSON 请求体区分缺失、false、0、空字符串和 null；GET 的 null 编码为空值，省略字段则不发送。文件响应需 `--output PATH`，完成后原子替换目标。

`--json` 成功输出 `{"ok":true,"data":...,"meta":...}`；失败信封写入 stderr，含错误类型、request_id 和 outcome_unknown；部分已知失败还附可选 error.hints。普通模式在 stderr 显示错误及 Hint。提示不改变原请求、错误码或结果未知状态，也不会自动重发写请求；网络错误或中断导致结果未知时先核验远端状态。Ctrl-C 返回 130，只停止本地进程。认证与秘密输出见 [accounts.md](accounts.md)。

225 个 HTTP 操作已实现；GetInferSetTerminal 和 GetInferSetLogsTail 暂不支持。日志跟随使用历史日志轮询，SSH 使用实际网关连接。`implemented-offline` 表示实现与离线覆盖，不代表真实平台验证。只有审计覆盖范围时才查 [支持矩阵](support.md)。

已知平台差异：

- 开发机列表的 `Creator` 条件会影响可见结果，见下方实测记录。空列表不能证明资源不存在；名称查找也受列表可见范围限制。
- 文件存储 `fs/alpha` 使用 yifs 路径和直接响应，详见 [storage.md](storage.md)。
- Ray 日志保留平台 JSON；不识别的跟随响应会报错，可用单次通用查询检查。
- 标量数组以重复查询键发送；实际服务端数组兼容性尚未联测。

基准为官方 Go SDK v0.5.1，固定提交 `8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5`。已实测 `.com.cn` HMAC、部分只读 API 和 Mac SSH/SFTP；临时 CPU 开发机创建、等待与删除，以及单副本 CPU Job 创建、运行、日志、跨任务 GPFS 产物验证、停止和删除已实测，详见 [jobs.md](jobs.md)。GPU/多副本 Job、Ray/Serving 写操作、Token 与服务账号认证尚未联测。225 个 HTTP 操作描述固定目录的实现范围，不表示线上控制台所有路由均已覆盖。

## 开发机列表与官方文档

官方文档入口为 [OpenAPI 文档中心](https://api.yicloud.com.cn/)。具体页面使用 `.html` 后缀；开发机列表见 [ListWorkspaces](https://api.yicloud.com.cn/workspace/list_workspaces.html)，详情见 [GetWorkspace](https://api.yicloud.com.cn/workspace/get_workspace.html)。网页文档可用于核对语义，CLI 字段验证仍以固定 SDK 目录为准；有差异时先记录并验证，不直接改生成文件。

实测省略 Creator 可能返回空，指定平台用户名后可见。默认筛选语义仍待确认，不对所有列表强加个人筛选；操作方法见 [workspace-ssh.md](workspace-ssh.md)。名称查找使用独立 `--lookup-set`，不会把列表过滤传给最终操作。

2026-10-19 核对官方 Job CreateJob 文档：TaskSpec.Command 是字符串数组；CLI 的 shell 模式是快捷参数约定，不是平台强制要求。官方历史日志接口使用纳秒时间，易读时间由 CLI 精确转换。当前核对的 API 文档未提供可据以确认 SSH 网关 rsync/TCP 转发支持的合同，本版不新增 sync/tunnel；需在用户指定的可用连接上另行验证。
