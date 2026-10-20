# 推理日志查询与下载

## 何时读取

查看部署日志、诊断启动问题或下载历史日志时读取。先按[管理手册](manage.md)取得唯一部署 ID；实例筛选标识从真实实例查询结果获得。

## 查询流程

未指定时间时，CLI 查询最近 10 分钟。用户明确要求“昨天”等范围时，先确定时区和日期边界，不套用默认窗口。

```bash
yicloud serving logs "$serving_id" --start "$start_time" --end "$end_time"
```

start_time/end_time 使用带时区 RFC3339 或 Unix 纳秒整数，由 CLI 转换。相对范围可用 `--since 15m`；与 `--start` 互斥。单次查询可用根级 `--json`；需要某个实例时加 `--instance "$instance"`，无需自己编码 API 的 Replicas。

默认 limit 可能截断繁忙窗口，按需要增加上限或拆分时间段。空结果不等于服务正常、没有输出或不存在；检查窗口、实例和查询错误，再结合 status、instances 判断。

## 下载

1. 查询 `api describe inferset DownloadInferSetLogs`。
2. 用真实范围、ID、时间和所需过滤构造完整请求文件。
3. 校验后调用并指定实际目标路径：

```bash
yicloud api call inferset DownloadInferSetLogs --file "$request_file" --output "$output_file"
```

该调用的请求字段以 describe 为准；输出可能替换目标文件，执行前确保路径符合用户意图。检查实际文件及内容后才报告下载成功。

## 协议限制与完成标准

GetInferSetLogsTail 和 GetInferSetTerminal 暂不支持。需要持续日志可用 CLI 的历史日志轮询 `--follow`，说明它不是 WebSocket 流；不能与 `--json`、`--dry-run`、`--end` 同用。不尝试用空 HTTP 握手模拟终端连接。

报告部署、时间范围、实例筛选和日志或文件结果。日志仅是诊断证据，不单独证明部署健康。
