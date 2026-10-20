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

快捷创建为单角色 t0、单副本、空 Env，命令默认使用 `sh -c`；需要登录初始化时显式加 `--login-shell` 才使用 `sh -lc`。镜像需提供 sh；请求文件的 Command 数组原样保留。配额模式快捷创建未传 `--gpu` 时显式发送 GPU="0"；显式 GPU 值、SKU 模式、Workspace、请求文件和通用 API 不受该默认值影响。复杂多角色、SSH、自愈和挂载用文件。`TaskSpecs` 是角色名映射，不是数组；其中 `SKUId` 与顶层 `SKUPublic` 的大小写不同。CPU/Memory/GPU 用资源量字符串。

资源模式以实时配额组和用户意图为准，可显式选择 `--use-private-machine` / `--no-use-private-machine`、`--qos Guaranteed`、`--priority 5`；Priority 为 1–9 的整数，API 中发送字符串。这些选项省略时不注入值，不能将“配额组名称已填写”当作模式、QoS 和优先级已选好。

短测试可加 `--max-wait-duration 2m --max-running-duration 2m`，分别传给 TaskSpec 的 MaxWaitDuration 与 MaxRunningDuration；接受正整数 s/m/h/d 并转换为等价秒字符串。它们是平台任务时限，与 `job wait --timeout` 的本地等待截止时间不同，进程内 alarm 也不能约束排队时长。所有快捷参数均与 `--file` 互斥；文件模式按官方字段填写。

确认目标是私有 CPU workload 配额组后，可用下列短任务预览请求；替换项目、可用区、镜像和配额组，不把该模式套用到其他资源组：

```bash
yicloud job create --name cpu-smoke --project PROJECT --zone ZONE \
  --image IMAGE --quota-group QUOTA_GROUP --cpu 1 --memory 8Gi \
  --use-private-machine --qos Guaranteed --priority 5 \
  --max-wait-duration 2m --max-running-duration 2m \
  --command 'python3 -u -c "print(sum([2, 3, 5, 7]))"' --dry-run
```

日志 API 的 Start/End 为 Unix **纳秒整数**；CLI 的 `--start/--end` 也接受带时区的 RFC3339（最多九位小数），如 `2026-10-19T10:00:00+08:00`。`--since 15m` 表示结束时间前 15 分钟，与 --start 互斥；支持正整数 s/m/h/d。默认最近 10 分钟、200 条，`--instance REPLICA` 过滤，`--follow` 每 3 秒轮询。一次查询可使用 `--json`，跟随模式拒绝 JSON。日志默认条数上限会截断繁忙窗口，需缩小时间范围或增加 limit；轮询采用时间边界和内容去重，不承诺高吞吐流量下严格恰好一次投递。

日志可能延迟进入索引，空响应不表示此前时段没有输出；跟随模式在没有有效时间戳时保留查询起点。排错时可用足够覆盖任务启动时间的单次查询交叉核验。

wait 默认间隔 5 秒、最多 30 分钟；`--no-timeout` 明确取消本地截止时间，与 --timeout 互斥。Succeeded 成功；失败终态、未知状态、本地超时分别返回 remote_failed、unknown_state、wait_timeout，带最后观察状态与时间。超时和 Ctrl-C 都不停止远端任务；恢复观察前重新查 status。删除使用 SDK 的 BatchDeleteJobs 并构造单资源列表，不虚构训练 start。

```bash
yicloud job stop JOB_ID --project example-project --zone example-zone
yicloud job delete JOB_ID --project example-project --zone example-zone --dry-run
```

查询“我的任务”使用 `job list --project example-project --zone example-zone --set 'Self=true' --all`，或 `--set 'Creators="PLATFORM_USER"'`（多个用户名逗号分隔）。默认项目列表可能包含其他创建者，不能当作个人列表。默认只取 20 条，检查 Total 与 Items，完整清单用 `--all`；个人筛选为空不等于项目为空。按名操作的同样过滤使用 `--lookup-set 'Self=true'`。

## 真实验证范围与创建差异

2026-10-20 在 `.com.cn` HMAC 环境完成单副本 1 CPU / 8Gi / 0 GPU 的真实闭环：文件模式生产 Job 创建、Running、日志、wait 至 Succeeded；另一个 Job 从 GPFS 读回 JSON 并验证内容/哈希，清理本轮文件和空目录后主动停止；两个任务删除后按 ID 确认不存在。该结果不代表 GPU、多副本、Ray 或 Serving 已通过写操作联测。

新版快捷入口也已独立实测：未传 `--gpu`，显式选择私有资源模式、Guaranteed、优先级 5 和两个 2m 时限后，创建、Running、wait Succeeded、日志标记及最终删除确认均通过。此前省略调度选项的请求曾持续排队并被清理；具体调度单因未确认，不能因此将这些值设为所有任务的默认配置。

当次请求携带顶层 RestartPolicy="Never" 和 BackoffLimit=0 时，本地校验通过但平台报 code=1001000「任务规格不合法」；仅移除这两个字段后创建成功。尚未区分具体字段单因，也不能推广为所有环境均不支持。CLI 会针对匹配的失败给出 hints，保留原请求和错误；改变这些字段前核对平台默认重试行为，不能为了提交成功擅自改变用户要求的执行次数。

文件请求在 CPU 配额模式下宜明确 GPU="0"；当次省略字段时平台报 code=100「任务资源参数错误」。结构化挂载与字符串挂载没有完成单变量对照；已通过本轮验证的是任务 MountGPFS 与顶层 Mount 使用相同的 `gpfs://CLUSTER/FILESET:/mnt/output` 字符串。路径必须由实时可访问文件集确定。

最小联测需验证真实文件内容，而不仅是成功状态或日志标记；验证持久化时可由独立后续任务读取同一文件并比对哈希。停止/删除请求成功后仍需确认最终状态，Failed=[] 不代表对象立刻不可见。只操作本轮唯一命名的任务和产物目录，保留脱敏复现证据及未验证范围。

来源：[官方 CreateJob API](https://api.yicloud.com.cn/job/create_job.html)、[官方日志 API](https://api.yicloud.com.cn/job/get_logs.html)、[创建自定义任务](https://docs.yicloud.com/4/1/1/2/1.html)、[SDK job](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/job)。
