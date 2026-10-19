# 模型部署

适用于持续推理服务。先确认模型版本、镜像、端口、探针、挂载和副本规格，保存完整请求文件，再 dry-run 和创建。拓扑与自动扩缩容用官方字段，不将训练 TaskSpecs 套入部署。

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

start/stop/delete 对应真实 SDK 接口。日志历史查询使用纳秒整数，默认最近 10 分钟，`--instance` 编码为 Replicas 数组。自动扩缩容使用 Create/Update/Get/DeleteInferSetScaleObject；先读取现有配置再变更。

GetInferSetTerminal、GetInferSetLogsTail 属于暂缓协议，会明确拒绝；不要把空 HTTP 握手视为已连接。历史日志下载使用 api call inferset DownloadInferSetLogs 并提供 --output。SDK 对部分返回类型使用泛化结构，客户端保留 JSON 数据，不据此推断健康状态；wait 遇到不认识的 Status 会报错。

来源：[创建部署服务](https://docs.yicloud.com/4/1/2/1/1.html)、[SDK inferset](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/inferset)。核对日期 2026-10-19；已实测 ListInferSet 空列表响应和内层 Data 数组形状，其余部署状态与操作尚未联机核验。
