# 可选 ProPainter 研究模式

默认快速模式不需要本页依赖。ProPainter 代码与权重采用上游自己的许可，不能因本项目许可而获得商用授权。

1. 阅读 https://github.com/sczhou/ProPainter/blob/main/LICENSE 。
2. 执行 `git submodule update --init vendor/ProPainter`。子模块固定为 `e870e79321c31b733e2031af5aa2fb1fe3ac7eec`，保留原始代码及许可。
3. 在已有虚拟环境执行 `.venv/bin/python -m pip install -r requirements-propainter-lock.txt`。这是此前 macOS Intel / Python 3.9 环境的版本快照，不保证其他平台都有对应包。
4. 按根目录 `weights-manifest.json` 的官方 release 地址下载三个权重到 `vendor/ProPainter/weights/`，并核对 SHA-256。记录中的摘要为本地下载核对值，不是上游发布的签名。
5. 重启应用，选择 ProPainter 研究模式。工作视频各边至少 128 像素且均为 16 的倍数。

启动适配器强制 CPU：已验证设备上的 MPS 路径缺少所需 Conv3D 支持。研究模式可能耗时很久；不要把没有百分比进展解释为必然卡死，可查看任务实际阶段并取消。

上游仓库及算法作者：Shangchen Zhou、Chongyi Li、Kelvin C.K. Chan、Chen Change Loy。项目：https://github.com/sczhou/ProPainter 。本仓库只提供独立网页与运行适配，不声称拥有该模型或可以授予其商业许可。
