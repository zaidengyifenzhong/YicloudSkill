# 复杂请求与通用 API

## 何时读取

专用命令无法直接表达所需嵌套请求，或需要诊断 API 原始结果时读取。已知工作流优先使用对应手册，不自行重做名称定位和分页。

## 发现与构造

1. 已知操作直接 `api describe SERVICE ACTION`；未知时限定 `api list --service SERVICE`，command 字段给出对应 CLI 路由，null 表示协议未支持。
2. 查询返回固定 SDK 的请求 schema 和引用定义，不含完整响应合同，也不保证线上服务端具有相同业务行为。
3. 用真实值构造完整 JSON。完整 `--file` 不注入 context，不能和字段参数、位置 ID 或 `--set` 混用。工作流中的 `--extra-file` 只补充字段，不能覆盖目标范围或 ID。
4. 字段命令的布尔值显式传 true/false，对象和数组传 JSON；`--set FIELD=JSON` 可表达 null，但不能与同一字段选项重复。

## 校验和执行

```bash
yicloud api call "$service" "$action" --file "$request_file" --dry-run
```

变量必须来自已确认操作和实际请求。检查方法、路径、参数及 validation_scope；本地校验不检查权限、容量、镜像、存储或运行结果。校验通过后，若是授权的写操作或需要执行的读取，移除 dry-run 调用。

无字段请求可省略文件；`--file -` 从 stdin 读取 JSON。文件响应必须提供 `--output`，其成功写入会替换目标文件。先确定该路径符合用户意图。

## 工作流边界

通用 API 按原始请求执行，不自动分页、不查名称，也不提供所有专用工作流的归属核验。使用前须可靠确定每个资源标识和范围；不能把它当作绕过 CLI 目标冲突检查的后门。

生成命令是否支持名称定位以帮助为准；job edit、workspace edit、serving update 使用 ID。分页 `--all` 只在支持的读取命令提供；API 自身的 All 字段对应 `--field-all`，两者不同。

## 结果与恢复

JSON 成功信封为 ok/data/meta，业务 data 仍遵循平台结构，不存在适用于全部接口的统一资源字段。错误在 stderr 的 error 中提供 kind、request_id、outcome_unknown，部分错误附 hints。

- outcome_unknown：先读取实际状态，避免重复创建或更新。创建查到同名对象还需核对创建时间和原请求配置；零条考虑可见延迟，多条先消歧，证据不足仍为未知。
- 未知响应：保留脱敏结构，不伪造空列表或成功对象。
- 本地枚举不接受平台新值：核对正式合同，读[兼容问题](compatibility.md)。`--allow-unknown-fields` 不绕过类型和枚举，不用它猜字段。
- 暂缓协议：明确不支持，不模拟连接成功。

报告实际调用结果和验证层次；实现支持不等于已完成该环境联测。
