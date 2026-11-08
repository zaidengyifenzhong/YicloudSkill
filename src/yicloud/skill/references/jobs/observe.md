# 观察训练、验证产物与结束任务

## 何时读取

等待训练、查看历史日志、验证产物、停止或删除已有任务时读取。仅需清单或状态时读[查询已有资源](../query.md)。

## 查状态、等完成

按[查询手册](../query.md)取得真实 `job_id`、`project`、`zone`；已有 ID 直接查询。以下显式传范围，也可由已确认的 context 提供。按名称定位时使用 `--by-name`，不猜 ID。

```bash
yicloud job status "$job_id" --project "$project" --zone "$zone"
yicloud job wait "$job_id" --project "$project" --zone "$zone" --timeout 1800
```

`wait` 默认每 5 秒轮询，最多等待 30 分钟；默认目标是成功完成，Running 不算完成。`--no-timeout` 取消本地截止时间，与 `--timeout` 互斥。失败终态或未知状态报错，保留实际状态。超时或 Ctrl-C 只结束本地观察，不停止远端任务；恢复时重新查状态，不重复创建。

## 等待和日志

```bash
yicloud job logs "$job_id" --project "$project" --zone "$zone" --since 15m
yicloud job logs "$job_id" --project "$project" --zone "$zone" --start "$start_time" --end "$end_time"
yicloud job logs "$job_id" --project "$project" --zone "$zone" --since 15m --follow
```

按目标选择相对时间、明确时间或持续观察。`--since` 与 `--start` 互斥；`start_time`、`end_time` 使用带时区 RFC3339 或 Unix 纳秒整数，由 CLI 转换。默认最近 10 分钟、最多 200 条；`--limit` 可取 1–10000，达到上限不能视作完整日志。繁忙窗口增加上限、缩小范围或用 `--instance "$replica_name"` 筛选。

需要持续观察时使用 `--follow`，它是轮询，不能与 `--json`、`--dry-run` 或 `--end` 同用，不承诺日志严格恰好一次。空日志可能是索引延迟，扩大到覆盖启动时间的单次查询交叉核对。

同一时间戳占满查询上限、无法继续推进时，CLI 保留已输出日志并报错退出；增加 `--limit`、筛选 `--instance`，或改用分段历史查询核对，不能把退出当作日志已全部读取。

## 失败取证

只在诊断需要时查询副本或训前检查。`replica_name` 来自本次 replicas 返回的真实 `Name`；`job_uid` 来自 ListJobs / GetJob 的 `Uid`，不把 JobId 当作这两个值。

```bash
yicloud job replicas "$job_id" --project "$project" --zone "$zone"
yicloud job get-job-replica --job-id "$job_id" --project "$project" --replica-name "$replica_name"
yicloud job precheck "$job_id" --project "$project" --zone "$zone" --set "JobUid=\"$job_uid\""
```

`precheck` 查询已存在任务的训前检查，不是提交前的资源预检。删除或重建前，尽力保存本任务的 status、运行窗口日志、所需副本详情，以及挂载、路径和权限证据。记录命令、错误、退出码及 request_id，隐藏凭据，不采集无关任务内容。

日志暂时为空时，在明确的有限时间内重查，不无限等待。区分用户主程序退出与镜像附带服务的警告：只有具体错误和退出信息能支持归因，例如 `python: not found` 与用户命令退出 127。运行环境中 `python3` 可用不证明 `python` 也可用，也不能只凭某个附带服务退出就认定主程序失败。

有限取证后按原授权处理：没有清理约定时，保留排错所需资源；已有明确清理约定时，执行约定范围内的清理，任务失败、取证失败或产物验证失败都不取消该约定。证据未取全时记录具体缺口，不先删除再取证。用户要求保留的任务不自动删除，也不将清理扩大到用户既有数据。报告时区分已确认原因和待验证推测。

## 验证产物

先取得任务声明的实际输出位置，按[存储手册](../storage.md)读取文件或对象。检查任务要求的结构、内容或哈希；日志中打印路径和 Succeeded 都不能证明文件存在。用户要求持久化时，应从后续消费环境读取同一产物验证。

输出缺失时，先检查挂载、写入路径和权限并保存证据，再按[失败取证](#失败取证)中的原授权处理资源。

## 停止与删除

确认唯一目标和已有授权后，只执行对应操作；先加 `--dry-run` 预览，通过后移除该选项执行。预览通过不证明权限或远端业务条件满足。

| 意图 | 操作命令 | 执行后的验收 |
|---|---|---|
| 停止训练 | `yicloud job stop "$job_id" --project "$project" --zone "$zone" --dry-run` | `yicloud job wait "$job_id" --project "$project" --zone "$zone" --target stopped` |
| 删除任务 | `yicloud job delete "$job_id" --project "$project" --zone "$zone" --dry-run` | `yicloud job wait "$job_id" --project "$project" --zone "$zone" --target deleted` |

停止不等于删除。Job 没有 start/restart；重新运行需按[训练执行](run.md)创建新任务，不把重跑当作原任务恢复。停止时若已自然成功，`--target stopped` 报告目标不符，交付实际终态。删除等待必须保留 ID，不能用 `--by-name`；它验证范围内完整清单已无该 ID，不证明输出数据已删除。清理产物是独立操作，只处理已确认归属且获授权的路径。

## 异常与交付

等待超时或 Ctrl-C 不会取消远端任务；恢复观察先重新查状态。权限失败或网络错误不代表资源已删除。报告资源 ID、最后观察状态、日志范围、产物验证结果，以及资源是否按要求保留或清理。
