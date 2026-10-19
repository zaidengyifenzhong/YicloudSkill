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

快捷创建为单角色 t0、单副本、空 Env，命令使用 `sh -lc`；镜像需提供 sh。复杂多角色、SSH、自愈和挂载用文件。`TaskSpecs` 是角色名映射，不是数组；其中 `SKUId` 与顶层 `SKUPublic` 的大小写不同。CPU/Memory/GPU 用资源量字符串。

日志 Start/End 为 Unix **纳秒整数**；默认最近 10 分钟、200 条，`--instance REPLICA` 过滤，`--follow` 每 3 秒轮询。一次查询可使用 `--json`，跟随模式拒绝 JSON。日志默认条数上限会截断繁忙窗口，需缩小时间范围或增加 limit；轮询采用时间边界和内容去重，不承诺高吞吐流量下严格恰好一次投递。

wait 默认 5 秒、30 分钟。Succeeded 成功；Failed/Stopped 失败退出；未知状态明确报错；Ctrl-C 只中止本地等待。删除使用 SDK 的 BatchDeleteJobs 并构造单资源列表，不虚构训练 start。

```bash
yicloud job stop JOB_ID --project example-project --zone example-zone
yicloud job delete JOB_ID --project example-project --zone example-zone --dry-run
```

来源：[创建自定义任务](https://docs.yicloud.com/4/1/1/2/1.html)、[SDK job](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/job)。
