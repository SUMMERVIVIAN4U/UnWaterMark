# UnWaterMark · Liuying

**Mark the watermark. Clean up the frame.**

A local video watermark removal tool: upload → mark → repair → download. Supports MP4 / MOV / M4V and common constant- and variable-frame-rate videos. Your footage stays on your computer.

[简体中文](README.md) · **English**

## Why try it?

- **Start with fast mode**: no model weights to download. Best suited to small marks and simple backgrounds.
- **Choose exactly where to repair**: rectangle, brush and eraser tools. Preview the first 30 seconds or process the full video.
- **Less format preparation**: handles common VFR inputs, rotation, pixel aspect ratios and audio/video start offsets while keeping the original upload.
- **Stay in control**: see processing stages, cancel jobs, retry failures, then compare and download results.
- **Explore model-based repair**: optionally connect the ProPainter CPU research engine.

Fast mode can produce smearing or flicker. The fixed mask does not track moving watermarks; results depend on the footage. ProPainter requires a separate installation and can be very slow on CPU.

## Quick start

Install **Python 3.9** and **FFmpeg / FFprobe** with `libx264`, and make sure the commands are on your PATH.

```sh
git clone https://github.com/SUMMERVIVIAN4U/UnWaterMark.git
cd UnWaterMark
python3.9 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
./run.sh
```

Open **http://127.0.0.1:8765**, upload a video, mark an area and click the full-video processing button. Fast mode is the default and needs no ProPainter installation. Use `PORT=8767 ./run.sh` to change the port.

Verified on macOS Intel / Python 3.9.6 / FFmpeg 8.1. Native Windows is not supported; other platforms have not been systematically tested. The app UI is currently in Chinese. [Optional ProPainter setup (Chinese)](docs/PROPAINTER.md) · [Test coverage (Chinese)](docs/TESTING.md)

## Current boundaries

| Area | Supported |
|---|---|
| Input | MP4, MOV, M4V; ≤ 100 MiB; 8-bit SDR; at most one audio track |
| Frame rate | 1–120 fps; common VFR inputs are converted to 30 fps and may repeat or drop frames |
| Conversion | Reasons are shown; originals are kept; re-encoding may change image quality |
| Unsupported | HDR, special display transforms, missing or irregular timestamps |
| Runtime | Single-user, local, sequential jobs; restarting interrupts unfinished jobs without checkpoint recovery |

Uploads and results remain in `runtime/` until you remove them. Monitor disk usage and do not expose the service directly to the internet. Selecting ProPainter before installing it will fail the job; its geometry requirements and CPU cost are described in the setup guide.

## Help make it better

Found a difficult video? Share reproduction steps, synthetic test cases or a pull request. **Useful to you? Leave a Star ⭐. Found a bug? Open an Issue.** Do not upload private footage or credentials.

[Contributing (Chinese)](CONTRIBUTING.md) · [Report an issue](https://github.com/SUMMERVIVIAN4U/UnWaterMark/issues)

Tests generate synthetic videos. Initialize the submodule for dispatch tests; model weights are not required:

```sh
git submodule update --init vendor/ProPainter
.venv/bin/python -m pytest tests -q
```

## License

**Source available · Noncommercial use under the license · Separate permission for commercial use.** Application-owned code uses [PolyForm Noncommercial 1.0.0](LICENSE); retain [NOTICE](NOTICE). The full terms define permitted uses. This is a source-available license, not an OSI-defined open-source license.

Contact [SUMMERVIVIAN4U](https://github.com/SUMMERVIVIAN4U) for commercial inquiries; a public Issue without confidential details is a starting point. ProPainter requires separate commercial permission from its upstream rights holders. This project's permission does not replace third-party licenses or automatically cover community contributions without commercial relicensing rights. [Third-party notices (Chinese)](THIRD_PARTY_NOTICES.md)

Independently developed; not affiliated with any online service of the same name.

For a registration-free trial, see [deployment notes](deploy/README.md). Each browser has private records; a shared export password unlocks only its own full results. Locked previews are short and visibly marked. Processing happens on the server; terminal jobs expire after 24 hours. Changing browsers or clearing site data loses access. Local mode requires no password and does not enable automatic cleanup.
