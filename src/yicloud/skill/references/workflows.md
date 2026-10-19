# 端到端任务与稳定资产

适用于从代码到训练产物、再到服务的连续工作。确定用户希望验收的文件、指标或服务响应，操作闭环以这些结果为准。

1. `account current` / `account check` 确认身份，`project list` / `resources zones` 定位范围。
2. 查询镜像、SKU、配额和节点，明确代码、数据、权重和输出路径。
3. 用 `workspace scp` 同步代码，或使用镜像/共享盘/S3 准备输入。
4. 准备 job.json，用 `job create --file job.json --dry-run` 检查，提交并记录返回 JobId。
5. `job replicas`、`job logs` 和 `job wait` 跟踪；失败时保留请求 ID，查看具体副本，核对训前检查。
6. 成功后通过 SSH/存储工具检查输出文件、内容、大小及训练指标。任务 Succeeded 本身不证明产物符合需求。
7. 需要推理时将固定模型版本与部署拓扑写入 serving.json，dry-run 后提交；检查实例和实际服务响应。
8. 按用户意图停止不再需要的开发机、任务或服务，确认持久盘与版本的保留条件。

```bash
yicloud --json job create --file job.json
yicloud --json job status JOB_ID --project example-project --zone example-zone
yicloud job logs JOB_ID --project example-project --zone example-zone --follow
yicloud job wait JOB_ID --project example-project --zone example-zone --timeout 1800
```

无限日志和 SSH 不能用 --json；一次查询可用固定 JSON 信封串联脚本。创建发生超时先列出远端任务，不立即重复创建。Ctrl-C 只结束本地进程，远端清理由显式 stop/delete 控制。

可选在用户项目维护 YICLOUD.md，记录跨会话仍有效的资产。建议字段：账号别名、项目、地域、可用区；代码/数据/权重/产物路径；固定镜像和资产版本；消费者与清理条件。凭据、临时日志、配额读数和运行状态不进入该文件。只在用户任务需要时创建，不在本 Skill 安装目录保存用户资产。

来源：[官方训练流程](https://docs.yicloud.com/4/1/1/2/1.html)、[部署流程](https://docs.yicloud.com/4/1/2/1/1.html)。
