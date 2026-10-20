# 观察训练、验证产物与结束任务

## 何时读取

查询训练状态、查看历史日志、验证产物、停止或删除已有任务时读取。

## 定位与状态

直接使用已知 JobId。按名称查找使用 `--by-name`；CLI 负责在项目、可用区内遍历分页并消歧。完整清单使用 `job list --all`；“我的任务”使用 `--set 'Self=true'`，按名操作对应 `--lookup-set 'Self=true'`。项目清单不等于个人清单。

```bash
yicloud job status "$job_id"
yicloud job replicas "$job_id"
```

仅在诊断需要时查 replicas 或 `job precheck --help`；precheck 查询的是已存在任务的训前检查，不是提交前的资源预检，所需 JobUid 从实际状态取得。

## 等待和日志

运行完成使用 `job wait "$job_id" --timeout 1800`；默认每 5 秒轮询，最多等待 30 分钟。`--no-timeout` 明确取消本地截止时间，与 `--timeout` 互斥。未知状态或失败终态按错误返回处理，不猜成功。

```bash
yicloud job logs "$job_id" --since 15m
yicloud job logs "$job_id" --start "$start_time" --end "$end_time"
```

以上是相对时间和明确时间两种选择。时间值使用带时区 RFC3339 或 Unix 纳秒整数；由 CLI 转换，不自行浮点计算纳秒。默认最近 10 分钟、最多 200 条；繁忙窗口应增加 limit 或缩小时间范围。实例筛选使用 `--instance`。

需要持续观察时使用 `--follow`，它是轮询，不能与 `--json`、`--dry-run` 或 `--end` 同用，不承诺日志严格恰好一次。空日志可能是索引延迟，扩大到覆盖启动时间的单次查询交叉核对。

## 验证产物

先取得任务声明的实际输出位置，按[存储手册](../storage.md)读取文件或对象。检查任务要求的结构、内容或哈希；日志中打印路径和 Succeeded 都不能证明文件存在。用户要求持久化时，应从后续消费环境读取同一产物验证。

输出缺失时保留任务和相关证据，检查挂载、写入路径和权限；不要先删任务再排错。

## 停止与删除

1. 确认唯一目标及用户的停止或删除意图。停止不等于删除，Job 没有 start。
2. 对 `job stop "$job_id"` 或 `job delete "$job_id"` 先加 `--dry-run` 校验，通过后执行。
3. 分别使用 `job wait "$job_id" --target stopped` 或 `--target deleted` 验证结果。若任务已自然结束，报告实际终态，不把“停止请求发出”当作已停止。
4. 清理产物是独立操作，只删除已确定归属和授权范围的路径。

## 异常与交付

等待超时或 Ctrl-C 不会取消远端任务；恢复观察先重新查状态。权限失败或网络错误不代表资源已删除。报告资源 ID、最后观察状态、日志范围、产物验证结果，以及资源是否按要求保留或清理。
