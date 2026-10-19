# Ray 任务

适用于 Ray 分布式作业。先确认镜像含匹配 Ray 版本，配置 HeadSpec/WorkerGroups、挂载和 Entrypoint，dry-run 后创建。按需复制 [ray.json](../assets/examples/ray.json) 或 [workers.json](../assets/examples/workers.json) 到用户项目，替换其中占位符。

```bash
yicloud api describe ray CreateRayJob
yicloud ray create --file ray.json --dry-run
yicloud ray create --file ray.json
yicloud ray list --project example-project --zone example-zone
yicloud ray status RAY_JOB_NAME --project example-project --zone example-zone
yicloud ray events RAY_JOB_NAME --project example-project --zone example-zone
yicloud ray instances RAY_JOB_NAME --project example-project --zone example-zone
yicloud ray logs RAY_JOB_NAME --project example-project --zone example-zone
yicloud ray workers RAY_JOB_NAME --project example-project --zone example-zone --file workers.json --dry-run
yicloud ray wait RAY_JOB_NAME --project example-project --zone example-zone
```

ray 资源直接用操作参数 JobName；列表的对应字段是 `RayJobName`，UUID `Id` 不能替代它。显示名称使用 `--by-name`，在列表的 `Namespace`（项目）、`ZoneId` 和 `DisplayName` 内精确匹配，再把 RayJobName 传入操作请求。workers.json 只提供 `WorkerGroups`，不可重复覆盖命令参数中的 Project/ZoneId/JobName。更新前读实际配置，避免清空其他组。

历史日志使用 GetRayJobLogs 的 Method=query_range，StartTime/EndTime 为纳秒字符串。SDK 没有响应结构，因此保留直接 JSON（若有 Data 则提取 Data）；跟随要求可识别 Items 日志集合，其他形状明确报错后使用通用 API 检查。Method=download 的通用调用需 `--output`，作为原始文件写入。WebSocket 不在首版范围。

失败时先看 events、instances 和日志；stop/delete 没有对应 start，重新提交需要新的创建请求。wait 以任务 Status 成功终态为准，RayClusterStatus=Running 不能证明作业成功。

个人范围使用 `ray list --project example-project --zone example-zone --set 'CreatorId="PLATFORM_CREATOR_ID"' --all`，CreatorId 是平台创建者 ID，不能套用 Workspace 的 Creator 用户名。默认分页 20 条，检查 Total/Items，完整清单用 `--all`；CLI 的 `--all` 仅遍历分页，不会设置需要管理员权限的 API 字段 All。按名操作可用同样的 `--lookup-set 'CreatorId="PLATFORM_CREATOR_ID"'`。个人过滤对非空资源尚未联测。

来源：[创建 Ray 任务](https://docs.yicloud.com/4/1/1/3/1.html)、[SDK ray](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/ray)。
