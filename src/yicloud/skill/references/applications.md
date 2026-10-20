# 容器应用托管

## 何时读取

用户需要管理平台 Service 容器应用时读取。InferSet 模型推理使用[部署手册](serving/create.md)，两种资源的 ID 和请求结构不能混用。

## 创建与管理

1. 明确项目、可用区、应用镜像、启动配置、端口、资源和访问范围。缺少真实参数时先补齐。
2. 用 `api list --service service` 查对应专用命令，复杂请求查询 `api describe service CreateService`。
3. 按[API 手册](diagnostics/api.md)生成完整请求，dry-run 后提交；从结果取得真实标识并读取 GetService。
4. 用户要求可用服务时查 ListServiceReplica，依据明确实例状态及适用的服务探测验证；不因请求成功即报告可用。

## 生命周期与副本

| 意图 | API 操作 |
|---|---|
| 启动 | ChangeServiceToRunning |
| 停止 | ChangeServiceToStopped |
| 调整副本 | UpdateServiceReplicas |
| 删除 | DeleteService |

先读取当前配置和状态，确定唯一目标与授权，再查对应 schema、校验、执行并复查。这里没有可直接套用的 `serving wait`；仅使用 Service 的实际状态语义观察，不能以 InferSet 状态代替。

## 异常与完成标准

创建超时先查是否已存在；写入目标不唯一时停止。实例未就绪时检查配置和诊断信息，不自动扩容或重建。报告资源标识、配置变化、实例状态和服务探测结果，指出尚未验证的层次。
