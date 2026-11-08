# 开发机管理

## 何时读取

启动、停止、重启或删除开发机时读取。创建见[创建开发机](create.md)，清单和状态见[查询已有资源](../query.md)；仅需连接现有机器时转到[连接手册](connect.md)。

## 查询和定位

按[查询手册](../query.md)取得真实 `workspace_id`、`project`、`zone`，先查目标当前状态与依赖；已有 ID 直接使用，按名称定位加 `--by-name`。以下显式传范围，也可由已确认的 context 提供。不要用本地 SSH 登记冒充平台列表。

```bash
yicloud workspace status "$workspace_id" --project "$project" --zone "$zone"
```

## 启停、重启和删除

只执行用户授权的操作。先用表中命令预览，通过后移除 `--dry-run` 执行，再运行对应等待；预览通过不证明权限、容量或远端业务条件满足。

| 意图 | 操作命令 | 执行后的验收 |
|---|---|---|
| 启动已有开发机 | `yicloud workspace start "$workspace_id" --project "$project" --zone "$zone" --dry-run` | `yicloud workspace wait "$workspace_id" --project "$project" --zone "$zone"` |
| 停止开发机 | `yicloud workspace stop "$workspace_id" --project "$project" --zone "$zone" --dry-run` | `yicloud workspace wait "$workspace_id" --project "$project" --zone "$zone" --target stopped` |
| 重启开发机 | `yicloud workspace restart "$workspace_id" --project "$project" --zone "$zone" --dry-run` | `yicloud workspace wait "$workspace_id" --project "$project" --zone "$zone"` |

默认等待目标是 Running；默认每 5 秒轮询，最多 1800 秒。可用 `--timeout` 调整，或用与其互斥的 `--no-timeout` 取消本地截止时间。停止等待要求 Stopped。未知状态或失败终态报错，不把“请求已受理”当作操作完成。

重启后一次 Running 观察可能仍是重启前状态；结合本次请求结果、状态变化和任务要求的连接验证确认恢复。Running 只证明平台状态；需要可用 SSH、命令或 GPU 时，按[连接手册](connect.md)验证对应能力，不能只凭 Running 报告环境可用。

## 删除及云盘边界

先确定删除目标和关联盘处理意图；只授权停止时不删除。固定 SDK 的 `DeleteWorkspace` 有可选布尔字段 `DelWithCloudVolume`，描述为“云盘移入回收站”；用 `api describe workspace DeleteWorkspace` 核对当前安装版本的字段。通过 `--set` 或 `--extra-file` 显式传入已授权的选择。例如要求不随开发机回收云盘时：

```bash
yicloud workspace delete "$workspace_id" --project "$project" --zone "$zone" --set 'DelWithCloudVolume=false' --dry-run
```

预览通过后，保留相同字段并移除 `--dry-run` 执行。仅在已授权随开发机回收关联盘时改为 `true`，不要为删除成功擅自改变该值。

```bash
yicloud workspace wait "$workspace_id" --project "$project" --zone "$zone" --target deleted
```

删除等待使用已保存 ID，不能加 `--by-name`；它确认完整范围清单已无该 ID，不证明云盘已物理销毁。另按[存储手册](../storage.md)核对用户要求保留或回收的盘。停机计费、盘保留与回收策略以最新飞书对应说明为准；不能用固定 SDK 字段推断保留期限、费用或可恢复性。

## 异常与完成标准

创建或生命周期写入超时、断连、Ctrl-C 后先在原范围查实际状态，避免重复操作；本地等待超时不会停止机器。权限失败或网络错误不能当作已删除。报告资源 ID、范围、最后观察状态、请求错误及 request_id（如有）、实际验证的连接/环境能力，以及开发机和关联盘的保留或清理结果；证据不足时明确缺口。
