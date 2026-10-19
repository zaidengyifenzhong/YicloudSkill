# 存储与路径

适用于准备数据、代码和产物。先区分本地路径、容器挂载点、GPFS 源和对象存储 URI；确保训练、开发机和部署使用的身份有相同资产访问权限。记录源到容器目标路径映射，任务完成后通过真实文件或对象验收。

```bash
yicloud api list --service volume
yicloud api list --service fs
yicloud api describe fs/alpha ListDir
yicloud api call fs/alpha ListDir --file list-dir.json
yicloud api list --service oss
yicloud api call oss ListBuckets
```

list-dir.json 示例：`{"path":"/example/shared","page":1,"pageSize":20}`。文件存储扩展服务名为 `fs/alpha`，实际路径产品为 yifs。ListDir → ListFiles、CreateFile → CreateFiles、DeleteFile → DeleteFiles、Set/GetFilesetQuota → FilesetQuota，不能从操作名拼 URL。路径使用小写 JSON 字段；响应可能直接包含 files/items/total，不能强制要求 Data 信封。

卷创建、回收、恢复和挂载前运行 api describe，确认删除是否影响关联任务。云盘与文件存储管理接口不等同于上传任意文件。开发机文件传输用 workspace scp；训练使用持久盘、共享文件存储或对象存储输入输出配置。

对象存储首版只实现官方 SDK 的 bucket 管理接口。对象传输使用官方 S3 兼容工作流，独立配置 S3 凭据和 endpoint，不把 Yicloud 网关 HMAC 凭据直接当作 S3 凭据。以下环境变量需由用户在受信任终端配置；不在资产文档保存秘密：

```bash
aws --endpoint-url "$YICLOUD_S3_ENDPOINT" s3 cp ./data.json s3://example-bucket/input/data.json
aws --endpoint-url "$YICLOUD_S3_ENDPOINT" s3 cp s3://example-bucket/output/result.json ./result.json
```

该命令依赖另行安装 AWS CLI 并按官方资料配置 S3 访问凭据。SDK 没有对象上传下载操作，CLI 不另造上传接口。

来源：[文件存储](https://docs.yicloud.com/4/3/1/2.html)、[对象存储](https://docs.yicloud.com/4/3/1/3.html)、[SDK services](https://gitee.com/yicloud-team/openapi-sdk-go/tree/8f8d27e2b466b7ceac5dacfa12900d03ad70e3d5/services)。
