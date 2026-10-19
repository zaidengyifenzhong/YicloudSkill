# 发现资源与选择规格

适用于提交前查询。先确认账号地域，列出可用区和项目，再查 SKU、配额组及节点。SDK 没有公开的地域列表操作，地域由账号配置或 `--region` 选择。

```bash
yicloud account current
yicloud project list
yicloud resources zones
yicloud project quota --project example-project
yicloud resources skus --project example-project --zone example-zone --set 'SKUType="gpu"'
yicloud resources quota-groups --project example-project --zone example-zone
yicloud resources nodes --project example-project --zone example-zone
yicloud resources available --project example-project --zone example-zone --set 'QuotaGroup="example-quota"'
yicloud api describe workspace GetPredict
```

示例中的名称、规格、SKUType 值需以实时目录和 `api describe` 为准。列表默认 Limit=20；使用 `--all` 遍历有 Limit/Offset 的接口。通用 `api call` 完全保留请求，不自动分页。`--set FIELD=JSON` 中字符串也要带 JSON 双引号。文件输入与字段快捷参数互斥。

SKU 和配额组是不同资源模式；不要同时设置 SKU 与 CPU/Memory/GPU/QuotaGroup。配额表示允许使用的上限，不能证明节点现在空闲。`GetPredict` 是调度预测，不是资源预留或创建承诺。查询与提交之间容量可能变化。

默认资源参数直接作为 ID；显示名需 `--by-name` 并明确项目、可用区，所有页精确匹配，无法唯一确定时报告候选。SSH 则使用本地连接登记时的资源标识。

来源：[SDK mc](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/mc)、[官方管理中心](https://docs.yicloud.com/)。核对日期 2026-10-19；实时容量未验证。
