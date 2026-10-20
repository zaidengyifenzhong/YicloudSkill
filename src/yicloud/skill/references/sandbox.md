# 沙盒环境与实例

## 何时读取

创建或管理 Sandbox 环境、实例、容量及预热池时读取。

## 准备与创建

先区分直接创建实例、复用已有环境、创建可复用环境三种意图，确认项目、资源、生命周期与网络需求。Sandbox 的 ProjectName 不等于其他接口的 Project。用户要求开发机访问沙盒时，在创建前确认支持的访问路径，不能创建后才发现网络不满足用途。

1. `api list --service sandbox` 查所需入口，读取 CreateSandbox 的 schema。
2. 直接实例按真实 Image 与 Resources 配置创建，不为了单次实例默认创建环境或预热池。Image 的 Uri 与 Ref/Source 分支按 schema 选择，不同时填写冲突形式。
3. 复用环境时先 GetSandboxEnvironment，使用实际 EnvironmentId；只有用户确实需要新的可复用环境才走 CreateSandboxEnvironment，校验后提交并保存真实环境标识。用户仅要求环境时，读取环境详情验证后结束，不额外创建实例或修改预热配置；平台随环境自动建立的预热池按实际结果报告。
4. 确实需要实例时，选择直接配置或实际 EnvironmentId 构造 CreateSandbox 请求，dry-run 后提交并保存新的实例 ID；用 GetSandbox 验证。环境 ID 不能代替实例 ID。
5. 只有存在实际 EnvironmentId 且任务需要时才查 GetInstanceStateStats、容量、预热配置及环境事件；这些环境接口不适用于没有环境 ID 的直接实例。配置上限不证明即时容量。

通用请求调用与未知结果恢复见[API 手册](diagnostics/api.md)。

## 调整与结束

UpdateInstanceCapacity、UpdatePrewarmSize、UpdateSandboxLifecycle 都是写操作，可能改变资源占用和存活时间。先读现有配置，对比用户要求，校验后提交并重查；不能为了创建成功自行增加预热池或延长生命周期。

停止/删除实例与删除环境是不同范围。先确认具体对象和依赖，读取对应操作定义，不把实例清理升级成环境删除。批量操作逐一核对目标清单。

## 网络与异常

Sandbox 与开发机不保证处于互通网络，按实际部署、出站策略和平台支持的访问方式核实。不能以改路由、隧道或放宽隔离绕过限制。包下载成功不证明业务服务连通。

启动失败按实例详情、ListEnvironmentEvents、预热事件及历史日志诊断；容量读取失败不能当作零或充足。写入超时先查真实状态，不重复创建。

## 完成标准

报告环境和实例标识、生命周期、实际实例状态及用户需要的连通性验证。预热容量配置成功与实例可用分别确认。
