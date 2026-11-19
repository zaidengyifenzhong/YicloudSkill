# 用 rjobv3 提交和管理自定义训练任务

适用于用户指定 `rjobv3`，或希望在已有开发机内用官方工具提交和管理托管训练的场景。平台 CLI 的配置和参数见[官方 rjobv3 指南](https://docs.yicloud.com/6/1.html)。若用户提供的是 `yicloud` 请求 JSON，按[训练执行手册](run.md)使用 `yicloud job create`。

## 在开发机内确认环境

- 用 `command -v rjobv3`、`rjobv3 --version` 和 `rjobv3 submit --help` 核对安装版本。官方目前仅支持在开发机内使用。若 GPU 开发机上的版本过旧，先说明官方升级需要重启及其影响，再按授权处理。
- 联网时显式设置 `YICLOUD_API_HOST`，从[平台域名信息](https://docs.yicloud.com/21/1.html)核对所属站点的 OpenAPI 网关。认证使用开发机已有的 `~/.auth/accesskey_id` 和 `~/.auth/accesskey_secret`，也可由已有的 `YICLOUD_PUBLIC_KEY`、`YICLOUD_SECRET_KEY` 提供。环境变量优先。避免读取或输出密钥值，`yicloud account` 别名不能用于这里。
- 项目用全局 `-p` 指定。省略时先取 `YICLOUD_PROJECT`，再取 `KUBEBRAIN_NAMESPACE`。实际提交需要 `--zone-id` 或 `YICLOUD_ZONE_ID`，资源组用 `--charged-group` 或 `KUBEBRAIN_QUOTA_GROUP`。用只读 `list` 核对目标范围，也要核对镜像与挂载路径是否可用。

## 先预览，再提交

先填入真实项目、资源组、镜像以及训练入口。以下调试示例以每个副本 2 核、1 卡、8 GiB 为例，按任务需求填写。`rjobv3 --memory` 的单位是 GiB。

```bash
rjobv3 -p "$project" submit --charged-group "$group" --image "$image" \
  --cpu 2 --gpu 1 --memory 8 --dry-run -- python train.py
```

`--dry-run` 在本地输出 YAML，需要项目和资源组，预览无需认证、可用区或 API 网关。检查镜像、资源、副本和启动命令。正式提交时核对目标项目与可用区，移除 `--dry-run`，记下返回的 `job_id`。预览无法证明线上配额、权限或镜像可用。

- `--` 后放容器命令。若训练命令包含 `-p`、`-o` 等与全局参数同名的选项，可用 `bash -c '…'` 包住完整命令，先确认镜像有 Bash，并核对预览中原样保留了参数。
- 多角色 Job 用 `---` 隔开各段。将镜像等共享配置放在公共段，角色的 `--task_name`、`--replicas`、资源及命令放在各自段。公共命令不会执行。各角色继承未覆盖的标量，同名环境变量和自定义资源由角色值覆盖，节点标签会合并。提交前逐个核对 `taskSpecs`。
- `--sku` 与 `--custom-resources` 互斥。选择 SKU 时只在确实需要覆盖平台规格时显式设置 CPU、GPU 或内存。优先级和抢占重试按任务要求及资源组限制设置。

```bash
rjobv3 -p "$project" submit --charged-group "$group" --image "$image" --dry-run \
  --- --task_name coordinator --cpu 2 --memory 8 -- python coordinate.py \
  --- --task_name worker --replicas 2 --gpu 1 --memory 16 -- python train.py
```

## 查询、排错和结束

```bash
rjobv3 -p "$project" -o json get "$job_id"
rjobv3 -p "$project" logs job "$job_id" -n 200
rjobv3 -p "$project" -o json events "$job_id"
```

- `list` / `get` 返回 Job、Task、Replica 层级。排队或失败时先看 `events` 中的调度和镜像事件，再读日志。副本事件可用 `events "$replica" --replica` 查询。若查询结果不完整，保留 Job 级事件继续排查。
- `logs` 查询近 7 天的文本日志。`logs replica` 实际查询所属 Job 的日志，按副本精确过滤时要核对日志内容。日志错误可能只打印 `[ERROR]` 而仍退出 0。自动化处理 `list`、`get`、`events` 和提交结果时用 `-o json`，日志和预览继续按各自格式处理。
- 获得明确目标后按 JobId 执行 `stop` 或 `delete`。停止释放资源并保留记录，删除会清除记录。按展示名查询时使用 `--name`，多条匹配先消歧。只有获授权处理全部匹配项时才用 `--force-all`。
- 结果未知时先在同一项目和可用区查询原任务，核对创建时间、配置和 JobId，再决定后续操作。验收训练结果时单独核实任务终态和持久化产物。
