# SSH 与 GPU 环境排错

## 何时读取

目标连接、登录初始化、GPU 工具或框架运行异常时读取。必须在出错的那台机器验证，不能用另一台 CPU 机器的结果代替。

## 诊断顺序

1. 先确认资源、连接和原始退出码。`workspace doctor "$resource"` 提供 SSH、当前目录磁盘与 NVIDIA 检查；unknown/skipped 不是通过或无 GPU。
2. 登录 shell 出错时，用 `workspace exec "$resource" -- uname -s` 区分 SSH 通道和镜像初始化故障。
3. `nvidia-smi` 找不到：检查当前 PATH、`command -v nvidia-smi` 和 `/usr/local/nvidia/bin/nvidia-smi`。
4. 绝对路径仍报告 `libnvidia-ml.so` 缺失：检查实际 LD_LIBRARY_PATH 及 `/usr/local/nvidia/lib`、`lib64`。不要递归搜索整个系统。
5. 设备或驱动错误：结合平台 GPU 分配、`/dev/nvidia*`、`/proc/driver/nvidia/version` 判断。需要修复驱动时单独确定范围，不把它当作普通依赖安装。

## 修复与验证

路径确实存在时，先在单次命令或子 shell 中加入所需目录，保留原变量，避免空路径元素。成功仅证明本次路径修正有效。

用户需要持久修复时，核对实际 shell 和启动文件，备份并做语法检查，再修改最小范围。用新建非交互 SSH、交互登录及重复加载验证，不把 Bash 的初始化规则套用到其他 shell。

`/etc/environment` 中声明变量不代表当前会话加载了它。`nvidia-smi` 成功也不证明框架可用；按任务执行最小设备识别和 GPU 运算。其 CUDA Version 不证明对应 Toolkit 已安装。

## 停止条件

主机密钥或签名警告不得通过关闭校验消除；分别检查命令退出状态和文件完整性。权限不足、未知驱动状态或初始化脚本错误，保留证据并报告具体层次，不自动提权、重启机器或改镜像。

完成时区分“连接恢复”“工具可执行”“框架运算通过”，列出尚存的初始化警告。
