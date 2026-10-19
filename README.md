# UnWaterMark · 留影

**圈出水印，让画面更干净。**

本地视频去水印工具：上传 → 圈选 → 修补 → 下载。支持 MP4 / MOV / M4V，兼容常见固定与可变帧率视频，素材留在自己的电脑上。

**简体中文** · [English](README.en.md)

## 为什么试试留影？

- **开箱即用的快速模式**：无需下载模型权重，适合小块水印与简单背景。
- **自己决定修哪里**：矩形、画笔、橡皮擦，先预览前 30 秒，再处理完整视频。
- **少折腾视频格式**：自动处理常见 VFR、旋转、像素比例与音画起点偏移，保留上传原件。
- **任务看得见、停得下**：查看阶段、取消、失败重试，完成后对比并下载。
- **想研究更复杂的修补？** 可选接入 ProPainter CPU 研究模式。

快速模式可能出现涂抹或闪烁；固定遮罩不会自动跟踪移动水印，效果取决于素材。ProPainter 需另行安装，CPU 处理可能很慢。

## 三步开始

先准备 **Python 3.9** 和带 `libx264` 的 **FFmpeg / FFprobe**，确保命令在 PATH 中。

```sh
git clone https://github.com/SUMMERVIVIAN4U/UnWaterMark.git
cd UnWaterMark
python3.9 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./run.sh
```

打开 **http://127.0.0.1:8765**，选择视频，画出区域，点击「处理完整视频」。默认快速模式无需安装 ProPainter；更换端口可用 `PORT=8767 ./run.sh`。

已验证：macOS Intel / Python 3.9.6 / FFmpeg 8.1。暂不支持原生 Windows，其他平台尚未系统验收。[ProPainter 可选安装](docs/PROPAINTER.md) · [测试覆盖](docs/TESTING.md)

## 使用前知道这些

| 项目 | 当前支持 |
|---|---|
| 输入 | MP4、MOV、M4V；≤ 100 MiB；SDR 8 位；最多一条音轨 |
| 帧率 | 1–120 fps；常见 VFR 转 30 fps，可能重复或丢弃帧 |
| 转换 | 展示转换原因；保留原件；重新编码可能影响画质 |
| 暂不支持 | HDR、特殊显示矩阵、缺失或异常时间戳 |
| 运行 | 单用户本地、任务串行；重启中断任务，不支持断点续作 |

`runtime/` 保存素材和结果，不自动清理。请留意磁盘空间，不要将服务直接暴露到公网。ProPainter 选项须完成安装后使用，否则任务会失败；其尺寸要求及耗时见安装说明。

## 一起把它做好

遇到不好处理的视频？欢迎提交复现步骤、合成测试素材或 PR。**觉得有用，点颗 Star ⭐；发现问题，开个 Issue。** 请勿上传私人素材或密钥。

[参与贡献](CONTRIBUTING.md) · [提交问题](https://github.com/SUMMERVIVIAN4U/UnWaterMark/issues)

完整测试会生成合成视频；初始化子模块用于调度测试，无需下载权重：

```sh
git submodule update --init vendor/ProPainter
.venv/bin/python -m pytest tests -q
```

## 许可

**源码公开 · 非商用按许可使用 · 商用另行授权。** 应用自有代码采用 [PolyForm Noncommercial 1.0.0](LICENSE)，请保留 [NOTICE](NOTICE)；具体许可范围以条文为准。这是 source-available 许可，不属于 OSI 定义的开源许可。

商用请联系 [SUMMERVIVIAN4U](https://github.com/SUMMERVIVIAN4U)，可通过 Issue 发起不含机密的咨询。ProPainter 的商业许可需另向上游取得；本项目授权不替代第三方许可，也不自动覆盖未获商业再许可的社区贡献。[第三方说明](THIRD_PARTY_NOTICES.md)

本项目独立开发，不隶属于任何同名在线服务。

免注册服务器试用见 [部署说明](deploy/README.md)：每个浏览器只看自己的记录，输入统一导出密码才能下载完整结果。未解锁时提供带标记的短片预览。视频在服务器处理，任务结束后保留24小时并自动清理；换浏览器或清除网站数据无法找回记录。本地运行不需要密码、不自动清理。
