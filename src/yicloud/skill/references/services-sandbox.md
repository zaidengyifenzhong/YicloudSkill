# 服务托管与沙盒

适用于容器应用、沙盒环境和预热实例池。使用通用 API；先枚举接口并描述请求，再以 JSON 文件调用。服务托管不等于模型部署，沙盒字段 ProjectName 不等于其他服务的 Project。

```bash
yicloud api describe service CreateService
yicloud api call service ListService --file services.json
yicloud api call service CreateService --file service.json --dry-run
yicloud api describe sandbox CreateSandboxEnvironment
yicloud api call sandbox ListSandboxEnvironments --file sandboxes.json
yicloud api call sandbox CreateSandbox --file sandbox.json --dry-run
```

services.json：`{"Project":"example-project","ZoneId":"example-zone"}`；sandboxes.json：`{"ProjectName":"example-project"}`。创建文件从 api describe 的嵌套 schema 准备，不将列表文件直接用作创建请求。

服务通过 ChangeServiceToRunning/ChangeServiceToStopped 启停，用 ListServiceReplica 核验实例，通过 UpdateServiceReplicas 修改副本数。API 的 Id 大小写不能替换为模型部署 ID。

沙盒先创建环境，检查实例容量和预热池，再创建沙盒；通过 GetSandbox、GetInstanceStateStats、ListEnvironmentEvents 和历史日志观察。UpdateInstanceCapacity、UpdatePrewarmSize 和 UpdateSandboxLifecycle 是写操作，可能影响资源占用；dry-run 只验证请求，不预留容量。

来源：[官方应用中心入口](https://docs.yicloud.com/)、[SDK service](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/service)、[SDK sandbox](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/sandbox)。
