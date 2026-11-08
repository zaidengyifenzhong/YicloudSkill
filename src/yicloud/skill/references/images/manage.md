# 管理镜像仓库与标签

创建仓库、删除仓库或版本、修改共享范围时读取。先按[镜像查询](query.md)确认目标项目、可用区、仓库和 tag；已有唯一目标不重复遍历。管理仓库元数据与[上传镜像层](publish.md)是不同操作。

## 准确命令

下列变量须来自用户意图及已核实范围。支持写入 dry-run，校验通过后在授权范围内对同一命令移除该选项：

| 目标 | 预览命令 |
|---|---|
| 创建仓库 | `yicloud --json registry create-custom-repository --project "$project" --zone "$zone" --repo-name "$repository" --scope "$repo_scope" --dry-run` |
| 删除单个 tag | `yicloud --json registry delete-image --project "$project" --zone "$zone" --repo-name "$repository" --tag "$tag" --dry-run` |
| 修改共享范围 | `yicloud --json registry update-custom-repository-visibility --project "$project" --zone "$zone" --repo-name "$repository" --scope "$visibility" --dry-run` |
| 删除整个仓库 | `yicloud --json registry delete-custom-repository --project "$project" --zone "$zone" --repo-name "$repository" --dry-run` |

Project 表示所属项目，不等于可见范围。创建的 repo_scope 按当前平台已确认策略和用户意图填写；该请求的 Scope 没有本地枚举，不能据此认定任意值都可用。用户要求保持个人私有时，不把项目共享当作私有，也不以更新接口支持的值反推创建接口全部策略。

[飞书镜像管理](https://iqeubg8au73.feishu.cn/wiki/E6aXw42RoiqM0SkdpP5cGIsJndc)区分两条路径：现有镜像共享注明当前最大范围为项目，不能共享到租户级；新建租户公共镜像另有创建流程，并可设置租户成员的推送权限。更新接口的本地枚举虽接受 `project`、`tenant`，也不能据此把现有个人仓库直接改成租户公共仓库。租户级需求先核实当前平台对应流程、账号权限和准确 API 映射；不以 `--scope tenant` 试写，也不擅自创建替代仓库。项目/租户公共都不等于互联网匿名公开，拉取范围和推送权限分别核对。

## 验证结果

- 创建后查对应自定义仓库列表核对实际对象和可见范围；创建仓库不代表已有镜像版本，更不表示已上传镜像层。
- 修改范围后读取真实 Visibility，按用户授权范围核对；鉴权或拉取失败不自动扩大可见范围。
- 删除 tag 与删除仓库分清；删除前核对依赖和用户要求保留的版本，不能顺带删除整个仓库。若连带删除语义或底层数据保留要求无法确认，先核实。删除后在原范围查询目标，权限/查询失败不作为删除成功。
- 写入结果未知时先查实际对象，避免重复建仓库或重复删除；报告请求是否被接受与实际核对结果，不把 dry-run 当作平台操作已完成。
