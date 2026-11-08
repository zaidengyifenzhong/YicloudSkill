# API 差异与异常处理

## 何时读取

通用 API 字段不匹配、未知响应、枚举或状态无法识别、个人筛选异常时读取。正常工作流无需预读本文；CLI 已处理的转换不由 Agent 重复执行。

## 基准与证据边界

请求目录固定于 Go SDK v0.5.1，commit `8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5`。`implemented-offline` 说明实现与离线覆盖，不代表每个操作经过真实联测，也不代表线上控制台所有接口已覆盖。

遇到与实时平台不一致的字段，保留请求 ID 和脱敏响应，核对对应官方定义；不要为了通过本地校验换成含义不同的值。开发回归和逐次测试记录不属于操作手册。

## 当前操作需要的差异

| 场景 | 规则与处理 |
|---|---|
| InferSet ID | 资源字段 ID，列表过滤字段 Id；不能全局替换大小写 |
| InferSet 项目 | 请求 Project，列表 Namespace；按名定位交给 CLI |
| InferSet Zone | Get/Start/Stop/Scale 不发 ZoneId；CLI 可用 zone 核对操作上下文，不自行向 API 补字段 |
| Ray 标识 | 操作用 JobName，列表为 RayJobName；UUID Id 不能替代 |
| 个人过滤 | Workspace Creator、Job Self/Creators、Ray CreatorId、InferSet Scope；不能互相套用或当作权限隔离证明 |
| InferSet 列表 | CLI 兼容 Data 数组及固定 SDK 的 GetInferSetLogsQueryRangeData；其他结构报错，不能当作空列表 |
| fs/alpha | 实际产品路径与操作名不同，使用 CLI 路由；直接 files/items/total 响应不强套 Data 信封 |
| 训练创建策略 | 某些环境拒绝特定 RestartPolicy/BackoffLimit 组合，按 hints 核对；不静默删除用户重试策略 |
| 文件集集群 | 六个 `fs` 文件集管理请求的 `FsCluster` 按官方 SDK 的可空字符串接收；`gpfs1` 常量不是封闭枚举，实际值从可用集群查询或已核实配置取得，其他枚举仍严格校验 |

### GPFS 集群字段

[固定官方 SDK 定义](https://gitee.com/yicloud-team/openapi-sdk-go/blob/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/fs/models.go)中，`CreateFilesetWithQuota`、`DeleteFileset`、`GetFileset`、`ListFilesetsWithQuotaInfo`、`SetFilesetQuota`、`UpdateFileset` 的 `FsCluster` 均为 `*string`，`binding` 仅为 `omitempty`，没有 `oneof` 约束。SDK 的 `gpfs1` 常量和注释此前被目录生成器推导为封闭枚举；CLI 通过有来源的定点覆盖移除这六处推导枚举，保留字符串类型、可空性、必填项及其他枚举校验，不维护固定集群名单。

[可用集群查询](https://api.yicloud.com.cn/fs/list_available_gpfs_clusters.html)用于发现目标可用区的真实集群。只读联测已确认 `GetFileset` 与带 `FsCluster` 的 `ListFilesetsWithQuotaInfo` 可使用查询得到的非 `gpfs1` 集群；详情按精确名称及集群返回，但列表可能仍包含其他集群，接受参数不证明筛选已生效，必须核对每项 `BucketResponse.FsCluster`。这不代表创建、删除、扩容或授权变更的当前业务规则已验证。[GetFileset 在线说明](https://api.yicloud.com.cn/fs/get_fileset.html)仍只列 `gpfs1`，不能把文档差异隐藏为全部平台合同已核实。

操作时核对真实文件集名称与 `FsCluster`，不把 Source、Id 或容器路径推导为集群，不换成另一个集群让请求通过。本地允许字符串不证明线上存在、可用或已获授权；写操作仍需核实目标、权限和最新业务限制。

## 状态、就绪与删除

未知状态按原值报告，不自行归类为 Running、Failed 或 Healthy。默认 wait 的运行或成功终态判断不替代业务验证。

普通 InferSet 副本等待使用官方详情的 Replicas、TotalReplicas、ReadyReplicas；缺少字段、类型不符或复杂拓扑时不能从泛化 JSON 猜就绪。[官方 GetInferSet 字段定义](https://api.yicloud.com.cn/inferset/get_inferset.html)明确区分总副本和就绪副本，真实推理仍需单独验证。

删除等待的可见范围证据不代表物理数据删除；权限变化、列表不完整或查询失败都不能算删除成功。资源归属核验不能证明的范围应明确报告，不隐去限制。

## 协议与日志

GetInferSetTerminal、GetInferSetLogsTail 暂缓支持；使用历史日志轮询或已有 SSH 能力，不能用普通 HTTP 空握手冒充连接。

CLI 日志选项负责 RFC3339/纳秒转换及实例编码。直接 API 请求才需要按 schema 使用纳秒整数/字符串、Replicas 数组等结构。Ray 跟随无法识别日志集合时，退回单次查询诊断，不假造时间戳。

## 完成标准

给出可复现的脱敏错误、具体不兼容点及当前可用路径。没有真实结果的行为标记未验证；不把离线合同通过写成平台已通过。
