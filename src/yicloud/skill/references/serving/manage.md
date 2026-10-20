# 查询与管理推理部署

## 何时读取

列出、定位、查询、启动、停止或删除已有 InferSet 时读取。

## 定位目标

优先使用已知 ID。完整清单使用 `serving list --all`，用户只要求“我的部署”时使用平台个人筛选：

```bash
yicloud serving list --set 'Scope="mine"' --all
```

项目从已确认 context 或显式 `--project` 获取。Scope 不等于 Workspace 的 Creator；不能把过滤参数当作权限隔离或归属证明。返回结果异常时核对范围，不擅自改查 global。

按名称定位必须显式 `--by-name`：

```bash
yicloud serving status "$deployment_name" --by-name --lookup-set 'Scope="mine"'
```

CLI 处理分页、范围匹配及名称消歧。没有匹配时报告未找到；多个匹配时补充范围，不挑第一项。查询失败不能解释为不存在。修改前取得真实 ID，后续等待删除使用 ID。

## 读取状态

```bash
yicloud serving status "$serving_id"
yicloud serving instances "$serving_id"
```

状态和实例是不同证据。需要持续观察运行状态时用 `serving wait "$serving_id"`；默认成功条件不代表实际推理已验证。只读任务不自动启动、扩容或修复资源。

## 启动、停止和删除

1. 读取当前状态，确认目标和用户意图。停止会影响正在使用该服务的请求；删除意图必须明确，不能把停止升级成删除。
2. 对对应 start/stop/delete 命令先加 `--dry-run`，检查目标请求；通过后移除 dry-run 执行。
3. 启动后等待默认运行状态；停止和删除分别使用：

```bash
yicloud serving wait "$serving_id" --target stopped
yicloud serving wait "$serving_id" --target deleted
```

这两条对应不同任务，按实际操作选择。删除确认有可见范围限制，不能把权限失败或列表解析失败作为删除成功。

## 异常与完成标准

写入结果未知时先查询；归属不匹配或无法核验时不通过通用 API 绕过。未知状态保留原值，必要时看实例和日志。报告目标 ID、实际状态与操作结果；删除部署不自动删除模型、镜像或数据。
