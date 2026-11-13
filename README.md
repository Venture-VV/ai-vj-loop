# AI VJ Loop

Library Loop 的完整开发交接：五尊 Tripo 雕像、程序化图书馆、三版灯光、Blender 脚本、成片与渲染证据。下一阶段是**复核整个脚本逻辑并重新设计灯光美术与激光**。

**先读 [HANDOFF.md](HANDOFF.md)**。用户最新反馈：第一版带激光的版本，主要问题是灯光美术和激光设计。已有渲染/文件检查通过不等于美术验收通过；这里保留全部版本供复核，不把任何旧版定为不能改的设计。

## 入口

- [开发 AI 交接与复核重点](HANDOFF.md)
- [源码、六步原任务书及详细说明](blender/library-loop/README.md)
- [本机实际执行记录（已脱敏）](docs/evidence/EXECUTION_REPORT.md)
- [全部交付文件与排除项清单](docs/evidence/publication-inventory.json)
- [来源、三次代码修改与版本关系](docs/PROVENANCE.md)
- [完整资源下载：GitHub Release](https://github.com/Venture-VV/ai-vj-loop/releases/tag/library-loop-handoff-20261113)

## 三版成片

| 版本 | 源场景 | 成片 | 说明 |
| --- | --- | --- | --- |
| 第一版：激光 | `library_loop_final.blend` | [library_loop_hero.mp4](https://github.com/Venture-VV/ai-vj-loop/releases/download/library-loop-handoff-20261113/library_loop_hero.mp4) | 用户要求重点复核：灯光层次、频闪与激光设计不满意 |
| 第二版：白脚灯 | `library_loop_white_reference.blend` | [library_loop_white_reference.mp4](https://github.com/Venture-VV/ai-vj-loop/releases/download/library-loop-handoff-20261113/library_loop_white_reference.mp4) | 用户反馈太暗、太闪、背景图书馆不可见 |
| 第三版：金色图书馆 | `library_loop_gallery.blend` | [library_loop_gallery.mp4](https://github.com/Venture-VV/ai-vj-loop/releases/download/library-loop-handoff-20261113/library_loop_gallery.mp4) | 稳定背景与柔和雕像照明，低幅度 10 秒循环；保留为对照 |

第四版（重设计，进行中）：`scripts/sanctum_lighting.py` 从第一版场景生成 `library_loop_sanctum.blend`，说明见 [blender/library-loop/README.md](blender/library-loop/README.md) 的“重设计版”一节。旧三版原样保留。

前三版均为 HERO 主画面，1920×744、300 帧、30 fps、10 秒，带原参考音乐。TOP 扫描场景不是三版最终成片的一部分。

## 取得完整工作区

源码和脱敏证据直接保存在 Git；Blender 场景、完整模型、参考素材、候选预览、所有完整渲染帧等保存在同仓库 Release。没有使用 Git LFS。

```bash
git clone https://github.com/Venture-VV/ai-vj-loop.git
cd ai-vj-loop
python3 tools/fetch_assets.py --list
python3 tools/fetch_assets.py --profile review
```

`review` 下载三版 MP4、全部场景与候选模型、参考素材、关键帧与执行证据。需要三版完整 PNG 帧序列时：

```bash
python3 tools/fetch_assets.py --profile all
```

需要 Python 3.12+。下载工具优先使用已安装的 `gh`，否则使用标准库 HTTPS；会核对 SHA-256、安全解包、恢复原目录结构，遇到本地不同内容的同名文件会停止，不覆盖你的修改。资源清单为 [RELEASE_ASSETS.json](docs/RELEASE_ASSETS.json)，哈希为 [SHA256SUMS](docs/SHA256SUMS)。也可以从 Release 手动下载并在仓库根目录解压 `.tar.gz`，三个独立 MP4 放到 `blender/library-loop/out/`。

## 查看与继续开发

```bash
cd blender/library-loop
python3 scripts/test_tripo_batch.py
blender -b library_loop_final.blend --python-exit-code 2 -P scripts/render.py -- --scene HERO --out renders/review_laser --start 166 --end 166
```

离线测试不发真实 Tripo 请求。场景已嵌入所选雕像；复核和修改灯光无需 API Key，也无需重新生成模型。原始 `.blend` 按字节保留，其中历史音频路径可能指向原 Mac；若换电脑需要在 Blender 中重新关联 `reference/audio_loop.wav`，或使用 `tools/relink_scene_assets.py` 另存可移植副本。`assemble.py` 会直接读取当前工作区的参考音乐。

完整渲染、追加 Tripo 消耗前仍需向用户说明预计时长/积分并确认。不要提交或保存密钥、会话链接、下载授权参数。历史任务书中“不要改灯光节奏/分镜”的限制已被本次“重新设计灯光美术与激光、复核脚本”的要求更新；不要把旧限制当成无法重做的理由。

字体及参考素材说明见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。
