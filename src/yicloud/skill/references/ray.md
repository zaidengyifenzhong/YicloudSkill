# Ray 作业与 Worker 调整

## 何时读取

创建、观察或结束 Ray 作业，以及调整 WorkerGroups 时读取。仅训练框架内部使用 Ray 不代表必须迁移到平台 Ray 作业。

## 创建与运行

1. 确定项目、可用区、真实镜像及 Ray 版本、Entrypoint、HeadSpec/WorkerGroups、资源和挂载。按任务实际拓扑选择，不从训练 TaskSpecs 推导。
2. 读取 `api describe ray CreateRayJob`，保存完整请求文件；字段必填性不代表平台业务条件已满足。
3. 执行 `ray create --file "$request_file" --dry-run`。核对后移除 dry-run 提交，保存实际作业标识。
4. 查询 status，要求作业结束时使用 wait；要求产物时按[存储手册](storage.md)验证真实输出。

Ray 操作参数使用 JobName，即列表中的 RayJobName，不能使用 UUID Id 替代。显示名通过 `--by-name` 解析。个人列表按已确认的平台创建者 ID 使用 CreatorId 过滤，不套用 Workspace 的 Creator 用户名。完整列表使用 `--all`；它不会启用需要管理员权限的 API All 字段。

## 观察与排错

```bash
yicloud ray status "$ray_job_name"
yicloud ray events "$ray_job_name"
yicloud ray instances "$ray_job_name"
yicloud ray logs "$ray_job_name" --since 15m
```

这些是按诊断需要选择的读取操作。默认 wait 以作业 Status 的成功终态判断，RayClusterStatus=Running 不证明作业成功。日志时间由 CLI 转换；跟随无法识别响应时使用单次查询，并按[API 手册](diagnostics/api.md)保留原始结构。

下载历史日志时查询 `api describe ray GetRayJobLogs`，以真实 JobName、范围和时间生成完整请求，Method 使用 `download`，通过 `api call ray GetRayJobLogs --file "$request_file" --output "$output_file"` 下载。检查实际文件内容后才报告成功；不能把查询模式的 JSON 输出当作已下载的日志文件。

## 修改 Worker

先读取现有组配置，明确用户要调整哪个组、保留哪些组。构造只包含该操作所需附加字段的文件；不能用空 WorkerGroups 作为安全默认值。

```bash
yicloud ray workers "$ray_job_name" --extra-file "$workers_file" --dry-run
```

校验通过且符合授权后移除 dry-run，随后读取实际配置和实例验证。文件不能重复设置命令负责的 Project、ZoneId、JobName；不确定整体替换语义时先核对接口合同，不盲目提交部分组。

## 结束与异常

stop/delete 分别先 dry-run，再在授权范围内执行；使用 `ray wait "$ray_job_name" --target stopped` 或 `--target deleted` 验证。Ray 没有对应 start，重新提交属于新的创建动作。写入超时先查状态；未知状态不算成功，清理仅针对明确归属的资源和路径。

报告作业与集群状态、Worker 调整结果或产物证据，不把集群可用当作用户作业已完成。
