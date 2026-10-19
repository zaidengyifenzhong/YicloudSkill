# 管理、权限、监控和账单

适用于管理员操作及读数查询。所有固定 SDK 的普通 HTTP 管理写操作均可通过 API 调用，平台按当前身份执行权限检查；本地不模拟管理员成功。先查询对象现状和影响范围，再检查请求文件，变更后重查。

```bash
yicloud api list --service mc
yicloud api list --service iam
yicloud api describe mc CreateQuotaGroup
yicloud api call mc CreateQuotaGroup --file quota-group.json --dry-run
yicloud api describe iam SetAccessKeyPolicy
yicloud api call iam SetAccessKeyPolicy --file policy.json --dry-run
yicloud api call bc GetOverviewConsolidation
yicloud api describe monitor GetMonitorData
yicloud api call monitor GetMonitorData --file metrics.json
```

GetMonitorData 要求 MetricName、StartTime、EndTime，时间类型和查询维度以 api describe 为准。账单 GetOverviewConsolidation、GetProvisionConsolidation、ListBillingDetails 等可查询；查询范围可能决定返回租户总量还是项目量，不能混用。

权限与资源池变更、删除账号、密钥策略更新属于平台写操作，不自动重试。写失败且 outcome_unknown=true 时查询当前状态后决定是否重发。dry-run 不执行权限探测，也不能保证后端业务条件满足。

CreateAccessKey 等接口可能返回新秘密，默认脱敏；用户需要获取时显式 `yicloud --show-secrets api call ...`，不要把结果提交仓库。创建 IAM 用户的 Password 必须来自受信任输入文件或 stdin，输出和错误都会脱敏已识别的秘密字段。

来源：[官方管理中心](https://docs.yicloud.com/)、[SDK mc/iam/monitor/bc](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services)。核对日期 2026-10-19；管理员权限及计费读数未联机验证。
