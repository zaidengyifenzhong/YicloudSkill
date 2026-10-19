# 自定义训练任务

适用于单机和多角色训练。先准备镜像中的环境和持久存储路径，明确任务退出条件；提交后保留 JobId，观察 Phase、副本、训前检查、日志及产物。

多角色或挂载请求可从 [job.json](../assets/examples/job.json) 复制到用户项目后修改。模板中的资源与路径均为占位符。

```bash
yicloud job create --name train --project example-project --zone example-zone \
  --image example/image:tag --command 'python /mnt/project/train.py' \
  --sku EXAMPLE_SKU --sku-scope public --dry-run
yicloud job create --file job.json
yicloud job list --project example-project --zone example-zone
yicloud job status JOB_ID --project example-project --zone example-zone
yicloud job replicas JOB_ID --project example-project --zone example-zone
yicloud job precheck JOB_ID --project example-project --zone example-zone --set 'JobUid="UID_FROM_STATUS"'
yicloud job logs JOB_ID --project example-project --zone example-zone --limit 200
yicloud job wait JOB_ID --project example-project --zone example-zone --timeout 1800
```

快捷创建为单角色 t0、单副本、空 Env，命令默认使用 `sh -c`；需要登录初始化时显式加 `--login-shell` 才使用 `sh -lc`。镜像需提供 sh；请求文件的 Command 数组原样保留。复杂多角色、SSH、自愈和挂载用文件。`TaskSpecs` 是角色名映射，不是数组；其中 `SKUId` 与顶层 `SKUPublic` 的大小写不同。CPU/Memory/GPU 用资源量字符串。

日志 API 的 Start/End 为 Unix **纳秒整数**；CLI 的 `--start/--end` 也接受带时区的 RFC3339（最多九位小数），如 `2026-10-19T10:00:00+08:00`。`--since 15m` 表示结束时间前 15 分钟，与 --start 互斥；支持正整数 s/m/h/d。默认最近 10 分钟、200 条，`--instance REPLICA` 过滤，`--follow` 每 3 秒轮询。一次查询可使用 `--json`，跟随模式拒绝 JSON。日志默认条数上限会截断繁忙窗口，需缩小时间范围或增加 limit；轮询采用时间边界和内容去重，不承诺高吞吐流量下严格恰好一次投递。

wait 默认间隔 5 秒、最多 30 分钟；`--no-timeout` 明确取消本地截止时间，与 --timeout 互斥。Succeeded 成功；失败终态、未知状态、本地超时分别返回 remote_failed、unknown_state、wait_timeout，带最后观察状态与时间。超时和 Ctrl-C 都不停止远端任务；恢复观察前重新查 status。删除使用 SDK 的 BatchDeleteJobs 并构造单资源列表，不虚构训练 start。

```bash
yicloud job stop JOB_ID --project example-project --zone example-zone
yicloud job delete JOB_ID --project example-project --zone example-zone --dry-run
```

查询“我的任务”使用 `job list --project example-project --zone example-zone --set 'Self=true' --all`，或 `--set 'Creators="PLATFORM_USER"'`（多个用户名逗号分隔）。默认项目列表可能包含其他创建者，不能当作个人列表。默认只取 20 条，检查 Total 与 Items，完整清单用 `--all`；个人筛选为空不等于项目为空。按名操作的同样过滤使用 `--lookup-set 'Self=true'`。

来源：[官方 CreateJob API](https://api.yicloud.com.cn/job/create_job.html)、[官方日志 API](https://api.yicloud.com.cn/job/get_logs.html)、[创建自定义任务](https://docs.yicloud.com/4/1/1/2/1.html)、[SDK job](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/job)。
