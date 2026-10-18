# 第三方软件与许可边界

根目录 LICENSE 仅适用于维护者有权许可的应用自有代码，不替代第三方许可。

|组件|用途|来源与许可|
|---|---|---|
|ProPainter（可选子模块）|研究修补模型|https://github.com/sczhou/ProPainter ，S-Lab License 1.0；保留子模块 LICENSE，商业许可须联系上游|
|OpenCV|快速 TELEA 修补|https://github.com/opencv/opencv ，本项目使用 4.11；保留安装包携带的许可和第三方说明|
|FFmpeg / FFprobe（外部安装）|媒体解码、探测、转码|https://ffmpeg.org/legal.html ，实际许可取决于构建配置；本仓库不捆绑其二进制或编解码器|
|Python 依赖|网页、图像、模型运行|requirements 文件记录所用包；各包保留自身许可|

依赖安装包可能包含更多第三方组件。再分发打包应用、FFmpeg 二进制、模型或权重时，应逐项保留相应版权和许可。本仓库没有提供这些组件的统一商业再许可。

发布内容不包含用户视频、运行日志、原站脚本/网络抓包、签名链接、私人测试记录或模型权重。
