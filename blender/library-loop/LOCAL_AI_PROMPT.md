# 给本地 AI 的任务书

把下面整段发给本地的 AI（Claude Code / Cursor 等）。它需要能在这台电脑上执行命令、读图片。

---

你要在这台电脑上把一条 10 秒的 Blender 循环视频做完：用 Tripo 生成五尊雕像，换进已经搭好的场景，用显卡渲染 300 帧，合成带音乐的 MP4。

## 背景

- 仓库 `Venture-VV/something-ventured`，分支 `claude/bold-faraday-dq38fy`，目录 `blender/library-loop/`。先拉这个分支。
- **先完整读 `blender/library-loop/README.md`**，里面有设计、分镜和每一步的命令。下面所有命令都在 `blender/library-loop/` 里执行。
- 场景是脚本生成的：布景、灯光、激光、镜头、标题、音乐都已经写好并在 Blender 4.2 / 4.5 / 5.3 上跑通。你**不需要也不要改节奏和分镜**（`animate_hero()` 里的拍点），只做下面的事。
- 云端做不了、留给你的三件事：生成 Tripo 模型、GPU 渲染、看着画面微调。

## 开始前先确认环境，并告诉我结果

1. Blender 可执行文件在哪、版本号（需要 4.2 或更新）。Windows 上一般不在 PATH 里，自己找到完整路径。
2. 有没有可用的显卡（Cycles 的 OPTIX / CUDA / METAL / HIP）。
3. Python 3 是否可用（`tripo_batch.py` 只用标准库）。
4. 环境变量 `TRIPO_API_KEY` 是否已设置。**只检查有没有，不要把它的值打印出来、写进任何文件或提交。** 没有就停下来让我去 https://developers.tripo3d.ai 创建并设置好。

## 第 1 步　生成场景

```
blender -b -P scripts/build_scene.py -- --out library_loop.blend
```

然后渲一帧确认能出图（第 166 帧是五尊全亮）：

```
blender -b library_loop.blend -P scripts/render.py -- --scene HERO --out renders/check --start 166 --end 166
```

把这张图给我看，并报告这一帧用了多少秒。

## 第 2 步　用 Tripo 生成五尊雕像

模型清单和提示词在 `tripo/assets.json`，必需的是五个 `hero_*`，文件最终要放在 `assets/models/<id>.glb`。

**首选：仓库里的批量脚本（Tripo API v3）**

```
python scripts/tripo_batch.py --dry-run
```

把 dry-run 打印的内容和预计花费告诉我，**等我确认后**再真正生成：

```
python scripts/tripo_batch.py --variants 2
```

必须知道的事实：

- 这个脚本是按 2026-11-12 的官方文档写的，**从来没有对真实接口跑过**。如果返回的结构和脚本预期不一样，它会原样打印并停下。这时去读 https://developers.tripo3d.ai/llms.txt 里对应的页面，按文档修脚本，并告诉我你改了什么。不要靠猜。
- 接口是 v3：`https://openapi.tripo3d.ai/v3`。旧的 v2 已于 2026-10-31 停用，网上的旧示例不要照抄。
- 雕像**不要贴图**：`texture: false` 且 `pbr: false`（`pbr` 默认是 true，会强制带贴图）。场景里会重新上大理石材质。
- `model` 必须显式指定，用 `v3.1-20260211`。
- 花费大约每个模型 30 额度（无贴图 10 + 精细几何 20）。五尊各两版约 300 额度。**单次运行超过 400 额度先问我。**
- 任务 id 存在 `tripo/tasks.json`。超时或中断后**重新运行同一条命令**来取结果，不要重新提交，否则会重复扣费。
- 如果魔鬼那尊被内容审核拒绝（错误码 2008），用温和版提示词重试：`--only hero_1_demon_rising --moderated hero_1_demon_rising`。

**备选：Tripo 官方命令行 `tripo-cli`（npm）**

如果我说用 CLI，或者脚本修不通：先运行 `tripo docs --llm` 和 `tripo --help` 读它自己的说明，不要凭记忆写参数。两点注意：它的**默认模型是 P2，一个模型要 100 多额度**，必须显式指定 `v3.1-20260211`；设置 `TRIPO_ANALYTICS_ENABLED=0`。提示词仍然用 `tripo/assets.json` 里的 `prompt` 加 `style_suffix`，输出文件按 `id` 命名放进 `assets/models/`。

**挑选**：每尊有两版时（第二版叫 `<id>__v2.glb`），把两版各导入渲一帧给我看，我选定后把选中的那个改名为 `<id>.glb`。

## 第 3 步　把模型换进场景

```
blender -b library_loop.blend -P scripts/import_tripo.py
```

脚本会自动缩放到目标高度、落在位置上、换成大理石（天使）或黑色大理石（魔鬼）材质、隐藏占位模型。可以反复运行。

然后渲这几帧给我看：1（只亮中间）、8（中间三尊）、21（外侧两尊）、166（全亮）、173（红蓝对切）、250（扫描线）、277（最后一击）。

检查并修正：

- **朝向**。Tripo 模型的朝向没有用真模型验证过。雕像侧着或背对镜头，就加 `-- --yaw 0`（或 90、180）重新导入；只有某一尊不对用 `-- --yaw-3 180` 这种写法。
- **左右**。1、2 号应该朝向中间（右），4 号向外（右）刺，5 号向外（右）倒。反了就加 `-- --mirror 1`（可写多个：`--mirror 1,2`）。
- **大小**。改 `SLOT_n` 空物体上的自定义属性 `target_height` 后重新导入，或改 `build_scene.py` 顶部 `SLOTS` 里的 `height` 后重建场景再导入。
- 面数太高导致很卡：导入时加 `-- --decimate 0.5`。

## 第 4 步　调画面（只在需要时）

真模型的受光会和占位模型不一样。允许你改的只有这些，都在 `scripts/build_scene.py`：

- 频闪太亮 / 太暗：`KEY_W`。
- 某组激光太亮 / 太暗：`bake_node(..., 倍数)` 那几行。
- 雾：顶部 `HAZE_DENSITY`，或命令行 `--haze`。
- 辉光：`setup_compositor()` 里 Glare 的 `Strength` / `Threshold`。

改完要重建场景再重新导入模型（两条命令）。每次改动后重渲上面那几帧给我看，**我说可以了再进入下一步**。

## 第 5 步　渲染 300 帧

先用第 1 步测到的单帧时间估算总时长告诉我，我确认后再开始：

```
blender -b library_loop.blend -P scripts/render.py -- --scene HERO --out renders/hero
```

```
blender -b library_loop.blend -P scripts/render.py -- --scene TOP --out renders/top
```

- 默认是 Cycles，脚本会自动启用找到的显卡。可以随时中断，重新运行会跳过已有的帧。
- 只要主画面就不渲 `TOP`。
- 太慢时的选项，按顺序考虑并先问我：`--samples 48`；或者用 EEVEE 重建场景（`build_scene.py ... --engine EEVEE`）。**EEVEE 的画面云端没验证过**，亮度、雾、辉光很可能要按第 4 步重调。
- 渲完检查：帧数是 300，抽看第 1、150、300 帧，确认没有黑帧或缺帧。

## 第 6 步　合成出片

```
blender -b -P scripts/assemble.py -- --hero renders/hero --top renders/top --out out/library_loop.mp4
```

```
blender -b -P scripts/assemble.py -- --hero renders/hero --out out/library_loop_hero.mp4
```

第一条是上下两联（和参考片一样），第二条只有主画面。加 `--loops 6` 得到循环六遍的一分钟版。告诉我文件路径、分辨率和时长。

## 规矩

- 不要提交 `.blend`、`renders/`、`out/`、`assets/models/` 里的模型、`tripo/tasks.json`（已在 `.gitignore` 里）。如果修了脚本，单独提交脚本并说明改了什么。
- 不要把 API key 写进任何文件、命令历史说明或提交信息。
- 任何一步失败，把原始报错给我，说明你判断的原因，不要跳过或用别的结果顶替。
- 花钱（Tripo 额度）和长时间渲染之前都先停下来等我确认。
