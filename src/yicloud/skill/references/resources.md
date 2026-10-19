# 发现资源与选择规格

适用于提交前查询。先确认账号地域，列出可用区和项目，再查 SKU、配额组及节点。SDK 没有公开的地域列表操作，地域由账号配置或 `--region` 选择。

```bash
yicloud account current
yicloud project list
yicloud resources zones
yicloud project quota --project example-project
yicloud resources skus --project example-project --zone example-zone --set 'SKUType="gpu"' --set 'Scope="project"'
yicloud resources quota-groups --project example-project --zone example-zone
yicloud resources nodes --project example-project --zone example-zone
yicloud resources available --project example-project --zone example-zone --set 'QuotaGroup="example-quota"' --set 'PoolName="example-pool"'
yicloud api describe workspace GetPredict
```

示例中的名称、规格、SKUType 值需以实时目录和 `api describe` 为准。支持分页的列表默认 Limit=20；其 `--all` 遍历全部页。各查询仅提供对应 API 支持的范围和分页选项。通用 `api call` 完全保留请求，不自动分页。`--set FIELD=JSON` 中字符串也要带 JSON 双引号。文件输入与字段快捷参数互斥。

SKU 查询的 Scope 省略时默认 public；仅传 Project 不会切换到项目 SKU。按所需范围显式设置 public/tenant/project，可用 ResourceType 按 workspace/job/ray 等用途过滤，空列表不能推断为其他范围也无资源。

配额组选择同时核对 UsageType（开发机 workspace，工作负载 workload）和 MachineType（CPU/GPU），不能仅凭组名选择。从 quota-groups 返回的资源池信息取得真实 PoolName 或 PoolId，再查询 available；二者至少提供一个，同时提供时 PoolId 优先。SDK required 数组未表达此组合约束。若节点或容量查询返回鉴权失败，记录“实时容量未知”，不能当作零容量或可用承诺。

SKU 和配额组是不同资源模式；不要同时设置 SKU 与 CPU/Memory/GPU/QuotaGroup。配额表示允许使用的上限，不是最小可创建规格，也不能证明节点现在空闲。`GetPredict` 是调度预测，不是资源预留或创建承诺。查询与提交之间容量可能变化。

本平台 H200 默认不连外网，按离线运行准备，不在 GPU 任务启动时依赖公网包源或模型下载。公网内容在可联网 CPU 上准备，内部源可达时可直接在 GPU 上补包，见[环境准备](internal-sources.md)。只有用户或目标资源的明确配置确认可联网时才调整此前提，其他 GPU 按各自资源池判断。无外网不等于无内网；分别核对目标机器对平台镜像仓库、共享存储及所需服务的可达性。

默认资源参数直接作为 ID；显示名需 `--by-name` 并明确项目、可用区，所有页精确匹配，无法唯一确定时报告候选。需要与列表相同的过滤条件时用独立的 `--lookup-set FIELD=JSON`（可重复）；它只用于名称查找，不传给最终操作。`--set` 仍仅用于最终操作，查找过滤不可覆盖 Project/ZoneId/Limit/Offset。SSH 则使用本地连接登记时的资源标识。按 ID 的 dry-run 不联网；`--by-name --dry-run` 会先执行只读查询解析 ID，但不提交写请求。

来源：[SDK mc](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/mc)、[官方管理中心](https://docs.yicloud.com/)。
