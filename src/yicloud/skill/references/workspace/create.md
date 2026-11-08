# 创建开发机

入口是 `yicloud workspace create`。用户明确要求新建时按其要求创建；只要求获得可用开发环境时，才考虑是否复用已有机器。仅预览或准备请求时止于 dry-run。

## 准备必要参数

确定名称、项目、可用区、镜像、资源模式及磁盘要求。已有真实值直接使用，缺什么才查什么；范围未定时按[查询手册](../query.md)发现候选。不要重新选择用户已指定的镜像、规格或配额组。配额模式使用用户已加入的开发机配额组；挂载 GPFS 是可选需求，只使用已确认目录，不为普通创建自动新建存储或修改成员权限。

H200 开发机按默认无公网准备，依赖下载和共享交付见[环境准备](../environment.md)；不使用 GPFS 时也需确认所选镜像或交付方式已满足任务依赖。

| 缺少的信息 | 对应命令或手册 |
|---|---|
| 开发机配额组或规格 | [资源选择](../resources.md)：配额组筛选 `UsageType="workspace"`、`MachineType="CPU"` 或 `"GPU"`；SKU 筛选必填 `SKUType="cpu"` 或 `"gpu"`，用途为 `ResourceType="workspace"`，Scope 沿用实际要求 |
| 公共/项目镜像仓库及版本 | [镜像查询](../images/query.md)：按开发机用途、CPU/GPU、实际项目和可用区查询，已有指定引用不重复选择 |

镜像使用版本查询返回的完整 ImageUrl，不从标签或网关猜 URL。多个候选涉及环境、费用或运行策略时按用户需要选择，无法判断才一次性补问缺少的选择；不选第一个或擅自换最新版本。

## 选择创建路径

- **快捷参数**：当前 CLI 固定发送新建 50Gi 系统盘，仅在用户需求接受此容量且字段都可表达时使用。平台控制台指南的系统盘是 100Gi，不能把 CLI 的 50Gi 当成控制台默认；要求按控制台创建或明确需要 100Gi 时使用完整文件，容量含义不明时先确认。配额模式使用 QuotaGroup、CPU、Memory、GPU；SKU 模式使用 SKU ID 和 public/tenant/project 的 scope，不混入配额资源量。纯 CPU 配额请求显式传 GPU 0，内存保留 `8Gi`、`512Mi` 等单位，不把 `8Gi` 写成 `8`。
- **完整文件**：自定义系统盘、数据盘、已有云盘或克隆、挂载、环境变量、RuntimeMode、Internet 等快捷参数未覆盖的需求。先查 `api describe workspace CreateWorkspace`，按实际需求准备完整 JSON；文件不注入 context，也不能与快捷参数混用。磁盘名、数据来源、存储类和挂载路径均取真实值；按需读[存储手册](../storage.md)。

快捷配额请求示例中，各变量须已取得真实值；`gpu` 是要求的数量，CPU 任务为 0：

```bash
yicloud --json workspace create --name "$name" --project "$project" --zone "$zone" \
  --image "$image" --quota-group "$quota_group" \
  --cpu "$cpu" --memory "$memory" --gpu "$gpu" --dry-run
```

SKU 请求保留名称、范围、镜像，把配额组与 CPU/Memory/GPU 参数替换为 `--sku "$sku_id" --sku-scope "$sku_scope"`。完整文件使用：

```bash
yicloud --json workspace create --file "$request_file" --dry-run
```

Workspace 没有创建时的 Command 或 TaskSpecs；需要启动后执行命令时进入连接手册。不要用 Job 请求结构创建开发机。

## 创建时挂载 GPFS

需要使用 GPFS 提供共享输入或持久化输出时，先确定真实 Source、容器内 Target 和读写权限；已有确认的映射直接复用。缺目录或权限信息时按[存储手册](../storage.md)查询，不从目录显示名、ID 或本地路径猜源 URI。未选择 GPFS 时不自动添加挂载或新建文件集。

多台开发机或 Job 可在访问与权限允许时[共用同一 GPFS 来源](../storage.md#多台机器共用同一目录)，无需逐机复制数据。

挂载使用完整请求文件，在 **Workspace 请求顶层**填写 `MountGpfsVolumes`。下面仅展示挂载字段，必须替换示例源与目标并合并到已准备的完整请求，不能单独作为创建文件：

```json
{
  "MountGpfsVolumes": [
    {"Source": "gpfs://cluster-example/fileset-example", "Target": "/work/data"}
  ]
}
```

dry-run 时核对挂载字段未丢失。创建后，在用户要求的可用性验证中从实际 Target 检查输入文件可读；需要输出时核实写权限。元数据可见或请求通过不等于已挂载成功；临时写入检查只在已授权目录进行并清理自己创建的文件。

## 提交与验证

检查 dry-run body 的名称、Project/ZoneId、镜像、资源模式和数量、磁盘与挂载是否符合用户要求。通过后，在已有授权内对**同一条快捷或文件命令移除 `--dry-run`**提交，不临时改路径或省略已要求字段。

从实际响应保存 WorkspaceId，并沿用创建请求的项目、可用区查询，不能被不同的当前 context 覆盖：

```bash
yicloud --json workspace status "$workspace_id" --project "$project" --zone "$zone"
```

仅要求提交时报告真实 ID 和已查询状态；需要机器运行可用时执行 `workspace wait "$workspace_id" --project "$project" --zone "$zone"`。Running 只表示平台状态，用户需要 SSH、GPU 或特定程序可用时，再按[连接手册](connect.md)验证相应能力。

创建响应超时或结果未知时，先按本次名称及项目、可用区查询，结合创建时间和请求配置核对是否已创建。暂时无结果或同名多条均不能立即重发，也不能冒认旧研究机器。等待超时不代表远端已停止，不自动删除重建。
