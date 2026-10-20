# 手动副本与自动扩缩容

## 何时读取

用户要求调整副本数或配置自动伸缩策略时读取。先区分两类意图：明确副本数使用 scale；按负载调整使用 ScaleObject 接口。

## 手动调整

1. 按[管理手册](manage.md)定位唯一 ID，读取当前 status 与自动扩缩容配置。目标副本数必须来自用户要求。
2. 存在自动策略时，判断它是否会覆盖手动目标；不得为了固定副本而自行删除策略。需要改变策略且当前未授权时说明取舍。
3. 对已取得的真实值校验请求：

```bash
yicloud serving scale "$serving_id" --replicas "$replicas" --dry-run
```

4. 校验通过且当前授权覆盖后移除 dry-run 执行。资源不足时报告错误，不擅自换规格或减少目标数。
5. 普通单机部署可以使用 `serving wait "$serving_id" --replicas "$replicas"` 验证配置、总数和就绪数一致。它不验证推理响应；分布式或 PD 模式不使用这个简单计数目标。
6. 复杂模式按实际拓扑查询 status 和 instances，并使用该模式的明确健康标准；缺少模式合同或字段时报告未完成验证。

## 自动策略

查对应接口的 describe 后，按[API 手册](../diagnostics/api.md)提交完整请求，不根据名称猜嵌套字段。

| 用户意图 | 操作 |
|---|---|
| 查看现有策略 | GetInferSetScaleObject |
| 新建策略 | CreateInferSetScaleObject |
| 修改策略 | UpdateInferSetScaleObject |
| 取消自动策略 | DeleteInferSetScaleObject |

读取现有策略后才修改或删除；新建前确认没有已有策略。核对上下限、阈值和时间规则，保留用户未要求改变的有效字段，执行适用 dry-run 后提交。删除 ScaleObject 不是删除 InferSet。

变更后重新读取策略，核对实际配置。配置保存成功不代表已发生一次扩缩容，也不代表所有副本就绪。

## 异常与完成标准

策略读取失败时不盲目覆盖；写入超时先读实际状态再决定下一步。未知状态、缺少就绪字段或不支持的拓扑均不能猜成功。报告目标、实际配置、就绪结果及未完成的业务探测。
