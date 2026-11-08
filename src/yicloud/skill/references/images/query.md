# 查询镜像仓库与版本

查询已有镜像、标签或为开发机与 Job 选镜像时读取。沿用已确定的项目、可用区和用户指定版本，已有完整引用不重新选镜像；缺范围先按[查询手册](../query.md)确定。

## 按目标定位命令

以下变量来自真实范围和查询结果；只执行缺少信息对应的步骤，不先加载全部 API 目录。

| 查询目标 | 命令 |
|---|---|
| 公共仓库 | `yicloud --json registry list-public-repositories --zone "$zone" --all` |
| 公共仓库的版本 | `yicloud --json registry list-public-images --zone "$zone" --repository "$repository" --all` |
| 当前项目的自定义仓库 | `yicloud --json registry list-custom-repositories --zone "$zone" --project-name "$project" --all` |
| 自定义仓库的版本 | `yicloud --json registry list-custom-images --zone "$zone" --namespace "$project" --repository "$repository" --all` |

已明确开发机用途时，公共仓库查询加 `--scene workspace --machine-type cpu` 或 `gpu`；推理用途使用 `--scene inference --engine "$engine"`，engine 来自已确定的引擎。未知用途不猜 Scene，不以缺字段的请求试错。公共 repository 不含 `library/` 前缀。

只看已知 tag 时，在对应版本命令加 `--tag "$tag"`；关键字和仓库名称筛选可能为模糊匹配，仍要核对真实项目、仓库和 tag，不选第一项。完整列表使用 `--all`；预览请求时移除 `--all` 再加 `--dry-run`，两者不能混用。

三个项目参数不能互换：自定义仓库查询是 `--project-name`，自定义版本查询是 `--namespace`，仓库管理写操作才是 `--project`。Context 只注入接口实际支持的 Project/ZoneId，不会替代 Namespace 或 ProjectName。

## 选择与交付

报告仓库、可用区、项目或命名空间、tag、完整 ImageUrl；按任务需要附带实际返回的摘要、架构、框架和 Python 等信息。ImageUrl 取真实版本结果，不能用 API gateway、仓库显示名或 RepositoryId 拼接。多个候选涉及架构、CUDA 或框架取舍时补齐需求，不擅自选择最新版本。

可见不等于运行目标有拉取权限或依赖兼容；仅查询时不登录 Docker、不拉取、不创建测试资源。将选定的完整引用交给[开发机创建](../workspace/create.md)或[Job 创建](../jobs/run.md)。未返回某字段就说明未查明，不补造 digest 或域名；权限/分页失败不当作空仓库。

[飞书镜像管理](https://iqeubg8au73.feishu.cn/wiki/E6aXw42RoiqM0SkdpP5cGIsJndc)还区分个人、共享、项目公共、租户公共及平台镜像；平台镜像仅集群管理员可推送。文档注明项目操作员仅可查看平台镜像和项目共享镜像，列表范围要结合当前角色解释，不能把不可见解释为全平台不存在。
