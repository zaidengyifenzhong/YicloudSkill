# 模型部署

适用于持续推理服务。先确认模型版本、镜像、端口、探针、挂载和副本规格，保存完整请求文件，再 dry-run 和创建。拓扑与自动扩缩容用官方字段，不将训练 TaskSpecs 套入部署。

创建请求可从 [serving.json](../assets/examples/serving.json) 复制到用户项目后修改。模板中的资源与路径均为占位符。

```bash
yicloud api describe inferset CreateInferSet
yicloud serving create --file serving.json --dry-run
yicloud serving create --file serving.json
yicloud serving list --project example-project
yicloud serving status INFERSET_ID --project example-project --zone example-zone
yicloud serving instances INFERSET_ID --project example-project --zone example-zone
yicloud serving scale INFERSET_ID --project example-project --zone example-zone --replicas 2 --dry-run
yicloud serving logs INFERSET_ID --project example-project --zone example-zone
yicloud serving wait INFERSET_ID --project example-project --zone example-zone
```

API 的资源字段为大写 `ID`，ListInferSet 的过滤字段却为 `Id`。Get/Start/Stop/Scale 接口不接收 ZoneId；便利命令仍要求显式 zone 作为用户操作上下文，按名称查找时用于过滤返回资源。通用 API 只发送其声明的字段。

按名定位使用列表元素的 `Namespace`（项目）、`ZoneId` 和 `Name`，取其 `ID`；请求项目字段仍为 `Project`。列表同时兼容平台实测的 `Data` 数组及固定 SDK 声明的 `GetInferSetLogsQueryRangeData` 数组，后者仅经过离线合同验证。

start/stop/delete 对应真实 SDK 接口。日志历史查询使用纳秒整数，默认最近 10 分钟，`--instance` 编码为 Replicas 数组。自动扩缩容使用 Create/Update/Get/DeleteInferSetScaleObject；先读取现有配置再变更。

GetInferSetTerminal、GetInferSetLogsTail 属于暂缓协议，会明确拒绝；不要把空 HTTP 握手视为已连接。历史日志下载使用 api call inferset DownloadInferSetLogs 并提供 --output。SDK 对部分返回类型使用泛化结构，客户端保留 JSON 数据，不据此推断健康状态；wait 遇到不认识的 Status 会报错。

个人部署使用 `serving list --project example-project --set 'Scope="mine"' --all`；Scope 的其他范围为 group/global，不复用 Workspace 的 Creator。默认只取 20 条，检查 Total 与返回列表，完整清单用 `--all`。按名操作使用 `--lookup-set 'Scope="mine"'`。个人过滤对非空资源尚未联测。

来源：[创建部署服务](https://docs.yicloud.com/4/1/2/1/1.html)、[SDK inferset](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/inferset)。
