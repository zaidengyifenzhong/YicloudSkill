# 为新任务选择资源

## 何时读取

用户需要创建资源，且项目、可用区、规格或配额组尚未确定时读取。连接现有机器或查询已有任务无需重新选择。

## 选择流程

1. 沿用用户已选账号和范围；缺失时查 `account current`、`project list`、`resources zones`。地域由账号或根级 `--region` 选择，没有地域列表命令。
2. 区分用户选择的是 SKU 还是配额模式，不混用两套配置。
3. 按真实项目、可用区查询候选；支持分页的命令用 `--all` 取得完整结果。

```bash
yicloud resources skus --project "$project" --zone "$zone" --set 'Scope="project"' --all
yicloud resources quota-groups --project "$project" --zone "$zone" --all
yicloud project quota --project "$project"
```

SKU 查询省略 Scope 时为 public，仅传项目不会自动选择项目 SKU。按用户所需范围选择 public、tenant 或 project；先查帮助确定用途筛选参数。

4. 配额组核对 UsageType 与 MachineType：开发机与 workload、CPU 与 GPU 不能仅凭名称区分。从返回结果取得真实 PoolName/PoolId，再按 `resources available --help` 查询容量。权限失败记为“容量未知”。
5. 若候选唯一且符合既有要求可继续；多个候选涉及价格、资源或运行策略取舍时让用户选择，不自行挑第一个。

## 判断规则

- SKU 模式不同时传 CPU/Memory/GPU/QuotaGroup；配额模式明确所需资源量。
- 配额是使用上限，不是当前空闲量或最小创建规格。调度预测也不预留资源。
- 空结果先检查项目、可用区、可见范围和分页，不直接认定平台没有资源。
- 不把一次测试成功的 QoS、优先级或私有资源模式设为所有任务默认值。
- 创建前根据目标资源核对镜像架构、必要网络和存储权限；需要准备离线依赖时读[环境准备](environment.md)。

## 完成标准

取得符合用户要求的项目、可用区、资源模式与真实规格标识，并区分“已知配额”“实时容量”“尚未验证的条件”。将选择传给对应任务手册，不能在资源选择阶段擅自创建。
