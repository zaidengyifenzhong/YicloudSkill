# 查询计算资源与选择规格

## 先确定范围与目标

查询 CPU/GPU 规格、配额组、资源池、配额或节点容量时读取；创建前也可用它补齐资源选择。已有资源的清单和状态使用[查询手册](query.md)。这里只查询，不创建、启停、调整配额或加入配额组。

沿用用户指定的账号、项目、可用区。缺失时按需查 `account current`、`context show`、`project list --all`、`resources zones`；候选唯一且符合意图可使用，多个候选只补问缺失范围，不自行选第一项。地域来自账号或根级 `--region`，没有地域列表命令。`--all` 只翻当前范围的分页，不遍历项目、可用区或 SKU Scope。

## 按意图直接查询

以下 `project`、`zone` 必须来自本次确认的范围。只执行当前需要的查询；例子查询项目级 GPU 开发机规格和配额组，按下表替换用途与机型。

```bash
yicloud --json resources skus --project "$project" --zone "$zone" --set 'Scope="project"' --set 'SKUType="gpu"' --set 'ResourceType="workspace"' --all
yicloud --json resources quota-groups --project "$project" --zone "$zone" --set 'UsageType="workspace"' --set 'MachineType="GPU"' --all
yicloud --json project quota --project "$project"
```

| 意图 | 首命令与必要信息 |
|---|---|
| CPU/GPU SKU 规格 | `resources skus`；必填 `SKUType="cpu"/"gpu"`，指定实际 Scope、用途、zone；`Scope="project"` 还需 Project |
| 可见配额组及关联池 | `resources quota-groups`；必填 Project，按 zone、UsageType、MachineType 过滤；从返回的 QuotaGroup、PoolId/PoolName 取得真实标识 |
| 项目配额和占用 | `project quota --project "$project"`；项目级，无 zone 参数；配额限制另查 `project quota-limit` |
| 指定组/池的节点资源 | `resources nodes`；显式 project、zone，组用 `QuotaGroup`，池用 `ResourcePoolId`，不要用 PoolId 替代此字段 |
| 单独查询资源池元数据 | 先看 `api describe mc ListResourcePools` 和 `mc list-resource-pools --help`；其范围字段为复数数组 Projects/Zones，不是 Project/ZoneId |

查询已选定的 GPU 开发机配额组节点时，`quota_group_filter` 是 `QuotaGroup=` 加真实组名的 JSON 字符串，例如 `QuotaGroup="group-a"`；组名必须来自本次查询，不照抄示例值：

```bash
yicloud --json resources nodes --project "$project" --zone "$zone" --set "$quota_group_filter" --set 'UsageType="workspace"' --set 'MachineType="GPU"' --all
```

按池查询时，将组筛选替换为 `ResourcePoolId=` 加真实池 ID 的 JSON 字符串；按目标用途/机型替换其他筛选。不因当前没有节点查询权限而扩大范围。

### 节点查询失败时先区分响应

`resources nodes` 对应固定 SDK 的 `GET /mc/v1alpha1/ListNodes`；[官方 SDK](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services/mc) 的请求字段是 `Project`、`ZoneId`、`QuotaGroup`、`ResourcePoolId`。不要因为字段注释出现 ProjectName 就换成未声明字段，也不要将配额组返回的 PoolId 原样作为请求字段名。

已验证的同一账号、项目和 zone 下，组查询返回 HTTP 200、`Code=0`、`Data.Items=null`、`Total=0` 和明确的 Limit/Offset；旧 CLI 的 `--all` 随后报 `Unrecognized list response`，错误 code 为空。这是客户端空列表兼容问题，不能归因于权限。CLI 现在仅对 ListNodes 的这个明确空页合同将 Items 规范化为 `[]`，单页和 `--all` 均保留其他响应字段；Total 缺失、非整数或大于零、分页偏移不一致等响应仍报错并保留 request_id。空页只表示该筛选范围没有返回节点，不能推断物理空闲 GPU 数量。

同次按池查询实际返回 HTTP 200、`Code=101`、`Msg=鉴权失败`，服务端 `_err` 明确要求租户管理员或项目管理员才能查询项目节点列表；这是该路径的平台授权限制，与上述组查询不同。这条响应未核实用户当前角色，也不证明其他范围的统一授权规则。保留必要筛选、错误码、HTTP 状态及 request_id 交由平台核查。CLI 不自动重试、换账号、扩大查询范围或关联节点。组元数据、项目配额和 SKU 可作为只读替代信息，分别按各自口径报告，均不能替代未取得的节点容量证据。

字段和值区分大小写，不能在不同接口间照搬：

| 目标 | SKU 的 ResourceType | 配额组/节点的 UsageType |
|---|---|---|
| 开发机 | `workspace` | `workspace` |
| Job | `job` | `workload` |
| Ray | `ray` | `workload` |
| Serving | 当前依据没有确认其 SKU 用途筛选值 | 当前依据没有确认各部署模式的配额用途映射；按[部署手册](serving/create.md)核对 |

SKUType 用小写 `cpu/gpu`，MachineType 用大写 `CPU/GPU`。SKU Scope 可为 `public/tenant/project`，省略为 public；只传 Project 不会选中项目 SKU。ResourceType 省略表示所有用途，不能把混合结果直接当作目标用途候选。不要猜 `ResourceType="serving"`，也不要把 `UsageType="job"/"ray"` 发给配额组接口。

只查询“我所在的组”时，配额组可加 `--set 'IsBelongsTo=true'`；可见组不等于当前用户已有使用资格。QuotaGroup 名称过滤是子串匹配，选择时核对完整标识、UsageType、MachineType、ZoneIds 和关联池，不按名称猜用途。多个合适候选涉及资源、价格或策略取舍时交由用户选择。

## 配额、占用与可调度容量分开报告

- `project quota` 返回的 QuotaStatus、SkuQuotaStatus 按各自字段报告。TotalQuota、AllocatedQuota、UsedQuota 或 SKU 的 Total/Requested/Used/Available 属于配额及占用口径，不是物理空闲容量；不混用单位或自行相减后称为“空闲 GPU”。`quota-limit` 的 MinQuota/MaxQuota 也不是最小/最大单机规格。
- 配额组中的 MachineCount、PodCount、QuotaStatus 是组级信息，不能据此保证某个请求可调度。需要节点信息时，在明确组/池范围内查 `resources nodes --all`，保留节点状态、维护/调度条件和资源字段的实际含义；节点数量不等于空闲机器数量，不展开用户实例或任务内容。
- `resources available` 映射 `mc ListQuotaGroupResourcePoolSharedNodes`：查询指定池中尚未关联目标配额组的节点，**不是通用空闲容量接口**。仅此目标才使用；先核对 `api describe mc ListQuotaGroupResourcePoolSharedNodes`，提供真实 QuotaGroup（本地必填）及 PoolId 或 PoolName（描述要求至少一个，二者同时传时优先 PoolId），并限定 project、zone。不把返回节点视为当前组已可使用的资源，也不为测试关联节点。
- `resources predict` 是开发机创建前资源预判。先读 `api describe workspace GetPredict`，必填 Project、ZoneId，其他调度字段来自已核实的目标配置；不猜无说明的 Pool、ResourceType 或单位。预测不预留资源，也不自动适用于 Job/Ray/Serving。
- 空结果先核对项目、zone、Scope、用途和分页，只能报告该范围未返回候选。权限失败、未知字段含义或未完成分页属于未查明，不能记为零容量；不切换账号、扩大权限或试发错误字段探测。

## 交付与创建衔接

报告查询账号与地域、项目/zone、用途和筛选范围，分别列出规格/配额组、已知配额及占用、实际验证的节点/调度条件和未查明项。候选只有本地 schema 依据时，明确其在线支持和权限尚未验证。

创建时将真实规格标识或配额组交给对应任务手册：SKU 模式不混传 CPU/Memory/GPU/QuotaGroup；配额模式明确资源量。另核对镜像架构、网络和存储权限；需要离线依赖时读[环境准备](environment.md)。不把一次成功的 QoS、优先级或私有资源模式设为通用默认。

平台政策优先核对用户指定的最新飞书文档；本地 help/schema 仅描述固定 SDK 请求合同，不证明当前服务端支持、权限或实时调度能力。
