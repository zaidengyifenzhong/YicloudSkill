# 镜像、模型和数据集

适用于创建前选资产和训练后登记版本。先查当前账号/项目/可用区可见资产，再取版本详情及存储位置；固定可复现版本，创建成功后查询核对。不要把示例镜像当作平台现有资产。

```bash
yicloud api list --service registry
yicloud api describe registry ListCustomRepositories
yicloud api call registry ListCustomRepositories --file repositories.json
yicloud api describe modelrepo CreateModelVersion
yicloud api call modelrepo ListModelVersion --file model-versions.json
yicloud api describe dataset CreateDataSetVersion
yicloud api call dataset ListDataSetVersions --file dataset-versions.json
```

repositories.json：`{"ZoneId":"example-zone"}`；model-versions.json：`{"Project":"example-project","ModelId":"example-model"}`；dataset-versions.json：`{"Project":"example-project","DataSetId":"example-dataset"}`。

模型版本登记使用 ModelPath；数据集版本使用 DataPath/StorageType。先确保对应路径存在、任务输出完整且消费者可读，再提交管理接口。API 登记并不意味着已完成大文件上传。

镜像可见性更新使用 UpdateCustomRepositoryVisibility；先描述字段和现有可见范围，按用户授权变更。删除模型/数据集版本或镜像标签前检查仍在使用该版本的任务与服务。

## 离线 GPU 环境准备

H200 默认不连外网。在可联网 CPU 开发机准备环境，保存为自定义镜像，再让 H200 开发机或任务使用该镜像；其他无公网 GPU 资源池同样适用。优先复用已有合适镜像；需要定制时采用以下流程。

1. 选择与目标 CPU 架构一致、CUDA/Python/框架版本适配目标 GPU 的基础镜像，在可联网 CPU 开发机安装固定版本依赖。没有 GPU 不代表应安装 CPU-only 框架；涉及 CUDA 编译的扩展需核对工具链和目标架构，CPU 上安装成功不证明 GPU 上可运行。
2. 将需随镜像携带的环境放在实际制作镜像的文件系统内。先查看默认排除规则，确认虚拟环境、用户目录和缓存是否被保存；不要假定挂载的云盘或共享目录会打包进镜像。大型模型和数据可提前放入目标 GPU 可读的存储，运行时使用本地路径。
3. 从开发机进程列表取得真实 ProcessId，通过控制台“制作镜像”或 `yicloud api call workspace ReleaseProcess` 保存到有写权限的镜像仓库，使用新版本标签。WorkspaceId、SSH 连接名、系统 PID 均不能替代 ProcessId。保存前排除凭据、SSH 私钥和临时认证文件。
4. 查询目标镜像标签及摘要，确认目标项目/可用区可见且能够拉取，再在 GPU 上验证框架识别设备、最小 GPU 运算及依赖导入。检查启动时的隐式下载；需要 GPU 才能完成的编译应预备离线源码、工具链和依赖。验证完成前保留环境准备机或可复现构建记录。

CLI 已提供制作镜像接口入口，无需假定 CPU 开发机预装 Docker：

```bash
yicloud workspace processes WORKSPACE_ID --project PROJECT --zone ZONE
yicloud api describe workspace GetReleaseExcludePatterns
yicloud api describe workspace ReleaseProcess
yicloud api call workspace ReleaseProcess --file release-image.json --dry-run
yicloud api call workspace ReleaseProcess --file release-image.json
yicloud api describe registry ListCustomImages
```

`release-image.json` 的字段示例（全部标识须替换为实际值）：

```json
{
  "ZoneId": "ZONE",
  "ProcessId": "PROCESS_ID",
  "ImageName": "registry.example.com/PROJECT/environment:VERSION"
}
```

`ReleaseProcess` 不接受 Project 字段；`GetReleaseExcludePatterns` 则需要 Project、ZoneId 及进程定位。可用 `ExcludePatterns` 提交自定义排除规则，具体匹配和合并语义需核对平台，不能假定它自动过滤全部秘密。请求成功只说明提交成功，需另查镜像结果；网关身份缺失或鉴权失败时核对账号及接口支持，不伪造身份请求头。制作镜像接口及 CPU→H200 迁移尚未真实联测，以上流程不代表已经完成兼容性验证。

可选 YICLOUD.md 记录固定镜像标签或摘要、模型版本、数据集版本、源路径、挂载点、消费者和清理条件；不记动态访问 Token 或临时下载 URL。

来源：[官方资产中心入口](https://docs.yicloud.com/)、[SDK registry/modelrepo/dataset](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services)。
