# 来源与版本

上游仓库：`Venture-VV/something-ventured`，分支 `claude/bold-faraday-dq38fy`，范围为 `blender/library-loop/` 和原参考录屏。该仓库的业务 Web App、数据库与部署内容不属于此次 VJ 交接。

| 提交 | 内容 |
| --- | --- |
| `40abd3f8f3018411a9410f85489f61880b376a79` | 本机接手时的场景生成、分镜、激光、占位预览与任务书来源 |
| `f345ee4ac9910e22a338813b69aa68baccd9459b` | 本机 Tripo API 恢复/去重/预算与下载验证，镜像法线兼容修复和离线测试 |
| `02c73fc38e4a3f15bdebd3bb5db1f7909c113844` | 白脚灯参考节奏版本，去掉激光和天花板灯管 |
| `f189263f4401f9571530532ce13846d32ff76951` | 金色图书馆的柔和照明、持续可见背景与缓慢闭环 |

对应补丁保存在 `history/`；最终源文件直接在本仓库 `blender/library-loop/`。本机临时编写的辅助脚本原先位于被忽略的 `out/`，此次也已作为源码交付，并保留原相对位置。

制作过程：占位场景 → 10 个 Tripo 候选 → 五尊选择与朝向修正 → 第一版激光 → 第二版白脚灯 → 第三版金色图书馆。用户最新要求对整个脚本和灯光美术重新复核，三版都是可比较的历史，不是不得修改的标准答案。

第三版设计时读取了下列开源项目的方法，未安装或执行这些项目、未整段引入其实现：

- [spite/looper，loops/4.js](https://github.com/spite/looper/blob/master/loops/4.js)：持续基础光与周期缓动。
- [VjLooper，core/signals.py](https://github.com/MatiasDelera/vjlooper/blob/main/core/signals.py)：基础值、幅度与相位分离；读取时仓库提交 `aeddf7e7a47ca9530eea0e01820cc9a86b7b8604`。
- [BlenderBeat，lighting.py](https://github.com/hfxstudios0001/blender-beat/blob/main/blenderbeat/visual/lighting.py) 与 [smoothing.py](https://github.com/hfxstudios0001/blender-beat/blob/main/blenderbeat/animation/smoothing.py)：主光、补光、轮廓光及平滑；读取时提交 `caf7f53124ed3fbbe6b340aebe86453ac953b446`。

这些方法参考不是对本片设计质量的背书。美术问题和后续复核重点以用户反馈及 `HANDOFF.md` 为准。
