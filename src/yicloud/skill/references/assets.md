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

可选 YICLOUD.md 记录固定镜像标签或摘要、模型版本、数据集版本、源路径、挂载点、消费者和清理条件；不记动态访问 Token 或临时下载 URL。

来源：[官方资产中心入口](https://docs.yicloud.com/)、[SDK registry/modelrepo/dataset](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services)。核对日期 2026-10-19；资产管理尚未联机验证。
