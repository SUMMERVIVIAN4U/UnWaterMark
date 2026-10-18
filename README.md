# UnWaterMark · 留影

本地运行的视频去水印与区域修补工作台。上传视频，绘制固定遮罩，选择快速修补或可选的 ProPainter 研究引擎，预览、处理并下载结果。

**源码公开，按 PolyForm Noncommercial 1.0.0 允许非商业使用；商用需另行取得许可。** 欢迎提交问题、改进和测试素材的复现方法。项目不隶属于任何同名在线服务，也不包含其服务器算法、模型或接口凭据。

## 功能

- 本机处理：网页、上传和任务存储默认只监听 `127.0.0.1`。
- 矩形、画笔、擦除遮罩；前 30 秒预览或完整视频处理。
- 默认快速模式：OpenCV TELEA 逐帧修补，无需模型权重。
- 可选 ProPainter：独立的 CPU 研究模式，需另行安装代码、依赖和权重。
- 常见 SDR 8 位输入准备：VFR 转 30 fps、应用正交旋转、校正像素比例、补齐奇数边缘、处理音画起始偏移。
- 保留上传原文件；展示转换原因；任务记录、取消、失败重试与结果下载。

快速模式对小区域、简单背景更合适；复杂纹理可能涂抹，运动可能闪烁。遮罩固定作用于整个视频，不自动跟踪移动水印，也不保证恢复被遮挡的真实内容。

## 快速开始

已验证环境为 macOS Intel、Python 3.9.6、FFmpeg 8.1。进程管理使用 POSIX API，暂不支持原生 Windows；其他平台与 Python 版本尚未系统验收。FFmpeg 必须包含 libx264，且 `ffmpeg`、`ffprobe` 在 PATH 中。

```sh
git clone https://github.com/SUMMERVIVIAN4U/UnWaterMark.git
cd UnWaterMark
python3.9 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./run.sh
```

打开 http://127.0.0.1:8765 ，保持默认的“快速模式”。快速模式无需初始化 ProPainter 子模块。可通过 `PORT=8767 ./run.sh` 更换端口。

网页仍展示 ProPainter 选项，只有完成 [可选安装](docs/PROPAINTER.md) 后才能使用；未安装时选择它会使任务失败。研究模式在 CPU 上可能非常慢，本机历史样例中 4 秒视频处理超过 20 分钟。

## 输入与运行限制

MP4、MOV、M4V，最大 100 MiB，SDR 8 位、1–120 fps、最多一条音轨。不支持 HDR、特殊显示矩阵和缺失/异常时间戳。转换会重新编码；VFR 或末帧停留转为 30 fps 时可能重复/丢弃帧。页面绘制与处理使用同一工作视频。

一次串行处理一个任务。服务重启会将未完成任务标为中断，不提供断点续作。`runtime/` 保存原件、副本、遮罩和结果，不会自动清理；请自行管理磁盘空间。不要直接暴露到公网：当前是单用户本地工具，不是具备账户隔离的生产托管服务。

## 测试

测试实时生成合成视频，不需要私人素材。完整测试中的 ProPainter 调度测试需要初始化子模块，但不运行大型模型：

```sh
git submodule update --init vendor/ProPainter
.venv/bin/python -m pytest tests -q
```

发布前结果与覆盖范围见 [测试说明](docs/TESTING.md)。仅通过这些场景不意味着兼容所有视频。

## 许可证与商用

应用自有代码适用 [PolyForm Noncommercial 1.0.0](LICENSE)，请保留 [NOTICE](NOTICE)。该许可证对非商业组织等情形有具体定义，以完整条文为准。它属于 source-available（源码可见）许可，不是 OSI 定义的开源许可。

商业使用请先向 [SUMMERVIVIAN4U](https://github.com/SUMMERVIVIAN4U) 申请单独书面授权，可在仓库提交不含商业机密的授权咨询 Issue。许可范围取决于实际权利归属。

ProPainter 采用独立的 S-Lab License 1.0，其商业用途需另行取得上游权利人许可，本项目维护者不能代为授予。第三方依赖及 FFmpeg 仍受各自许可证约束，详见 [第三方说明](THIRD_PARTY_NOTICES.md)。

欢迎通过 Issue 和 Pull Request 共建；提交前请阅读 [贡献说明](CONTRIBUTING.md)。
