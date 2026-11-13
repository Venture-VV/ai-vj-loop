# Library Loop 本机执行记录

仓库：Venture-VV/something-ventured；原始分支 claude/bold-faraday-dq38fy；源提交 40abd3f8f3018411a9410f85489f61880b376a79。

## 授权与画面约束

- 用户确认：五尊雕像各两版，共 10 个候选，Tripo 总预算 300 积分。
- 用户随后明确“我需要渲染300帧，直接做”。执行 HERO 主画面，1920×744、30 fps、10 秒。
- 保持原有灯光节奏、拍点、镜头和分镜；模型朝向/镜像依任务书修正。
- 用户明确选择米迦勒第二版，并接受其单手举剑造型。
- API Key 只经本机密码表单进入当前进程内存；不写入文件、命令参数、日志或提交。curl API 认证通过 stdin；下载子进程不继承 API Key。

## 环境与初始预览

- Blender 5.3.0，Apple M4 Metal GPU，32 GiB RAM。
- 原始场景生成成功：79 objects，300 frames @ 30 fps。
- HERO 第 166 帧占位模型预览：1920×744，完整命令墙钟耗时 46.71 秒。

## 生成期间的错误与处理

原始查询错误：

```text
RemoteDisconnected: Remote end closed connection without response
```

任务 ID 保留；只读查询有限重试，创建请求不自动重试。国内 API 使用 https://openapi.tripo3d.com/v3。

原始下载完整性错误（代表记录）：

```text
Invalid or incomplete GLB download: hero_3_michael_dragon.glb
Invalid or incomplete GLB download: hero_3_michael_dragon__v2.glb (received=11287523, declared=11319444)
Truncated byte range bytes 0-1048575/11319444: received 900013
```

改用本机 curl HTTP/2 下载并校验 GLB magic/version/声明长度；完整文件验证通过后才原子替换目标路径。无重新生成、无重复付费。

第五个创建请求连接中断，未收到 task_id。停止后续提交，通过同一 API Key 的用量历史找到唯一对应请求时间的已成功任务 b732e857-482a-46eb-a881-203c544ed5ce，30 积分；恢复到原任务，不重复创建。证据：tripo-submission-recovery.json。

后续 CDN 连接错误：

```text
curl: (16) Error in the HTTP2 framing layer
curl: (28) SSL connection timeout
curl: (35) LibreSSL SSL_connect: SSL_ERROR_SYSCALL in connection to openapi.cdn.tripo3d.com:443
curl: (22) The requested URL returned error: 503
```

直连与代理探测均曾失败；重新查询原任务结果后成功取回同一文件。

## 本地代码修正与验证

- 顺序完成任务、预算检查、失败立即停止；失败与提交不明均保留任务记录。
- 状态文件原子写入；创建响应丢失时禁止盲目重提，可先只读对账。
- curl 通过 stdin 接收认证，创建请求不自动重试；GET 查询与已有模型下载可有限重试。
- 下载校验完整 GLB，避免将截断文件视作完成。
- Blender 5.3 不提供 Mesh.flip_normals；镜像导入改用 bmesh.ops.reverse_faces。普通/镜像立方体检查均保持向外的 signed volume=8.0，底部落地为 0。
- 13 项离线测试通过；无真实 API 请求或真实密钥参与测试。新增对账读取时，一次旧测试断言（预期不发任何请求）失败；更新为仅允许 GET 且禁止重新 POST 后全通过。

## 模型生成完成

- 十个候选全部下载，GLB 头、版本、文件长度、JSON 与网格完整性核验通过，总计 87.71 MiB。
- 账户起始 600、冻结 0；完成后可用 300、冻结 0，实际消耗 300 积分。多次断线仅恢复原任务，无重复生成。
- out/tripo-billing.json 中 elapsed_seconds 仅是最后一次恢复会话，不代表整个生成阶段。
- 密钥已随本机输入进程退出释放；后续场景与渲染无需再提供。
- 采用 1B / 2A / 3B / 4B / 5B。米迦勒 B 为用户明确选择，其余由助手根据用户“直接做 / 继续”指令选择。
- 选中的模型已按任务书放在 assets/models/<id>.glb；被替换的第一版另存为 <id>__v1.glb，第二版 __v2.glb 保留，见 final-models-manifest.json。Tripo 任务日志保留原始生成记录；无需再执行生成命令。
- 两组候选的场景第 166 帧均已渲染，A 总墙钟 34.27 秒，B 37.52 秒（含导入和保存）。
- 持矛 B 使用 yaw=90、mirror=4 修正朝向；路西法 B 保留 yaw=-90，其背面试渲另存而不用于成片。
- 候选比对图：renders/candidate_comparison.png。

联系表辅助脚本出现并修正 Blender 5.3 参数错误（只影响排版，不影响模型或场景）：

```text
TypeError: StripsTopLevel.new_effect(): ... invalid keyword argument(s) (frame_end)
AttributeError: 'TextStrip' object has no attribute 'align_x'
```

依据本机 RNA 接口改为 length=1、alignment_x / anchor_x / anchor_y，重新执行成功。

## 最终交付

- 最终场景：library_loop_final.blend，1920×744、30 fps、Cycles 96 采样。
- 原场景与导入后的八个时点物体、镜头、灯光、材质动画摘要相同，见 scene-validation.json；没有调整灯光节奏、分镜、亮度、雾或辉光。
- 七个任务书关键帧均渲染并目视检查，单帧平均 33.97 秒。联系表：renders/final_checks_contact.png。
- 300 帧 HERO 渲染已在 2026-11-13T00:36:16.871989+00:00 启动，复用同一最终场景已验证的七帧。预计其余 293 帧约 2.76 小时。
- 实时状态：render-status.json；原始渲染日志：render-hero.log。完成后自动验证全部 PNG 并合成带音乐 MP4。
- 交付完成。


## 完成验收

- 300 帧 HERO 完成；连续渲染、帧校验阶段 7,372.53 秒（约 2 小时 3 分钟），另有先前的七帧检查。合成及元数据验证约 15 秒。
- 300/300 PNG 文件名、1920×744 尺寸、PNG 全部块 CRC 与像素解压长度通过；零缺帧、零空文件。
- 300 张 PNG 全部加载，未发现意外的全黑或非数值画面；首帧、150 帧和 300 帧目视检查通过。
- 对实际 MP4 的第 1、150、300 帧解码并与源 PNG 比对，画面、标题和色彩正常。H.264 为有损压缩；RGB RMSE 约 0.0135 / 0.0246 / 0.0137。
- 视频：1920×744，30 fps，300 帧，10.000 秒，H.264；音轨：AAC，48 kHz，双声道，约 10.027 秒（编码尾部），可解码且非静音。
- 成片 out/library_loop_hero.mp4，18,514,387 字节，SHA256 13cafb576d1d2de827952952a00c37306a3bfaf3010b92c6d9769182ab3b2ed4。
- 最终场景 library_loop_final.blend，SHA256 611eb0e46f572ed00260d56d67ed78860256868c79c69e63f461eda82f84ca0b。场景与成片均在本机 SSD；未推送模型、视频或 .blend 到 Git。
- 只渲 HERO 主画面，未生成 TOP 上联。原始占位场景 library_loop.blend 保留。
- 修复脚本的本地提交：f345ee4ac9910e22a338813b69aa68baccd9459b；未推送远端。仓库工作区干净；场景生成、render.py 与 assemble.py 未改变。
- 生成造型未逐字实现提示词：米迦勒单手举剑已获用户接受；魔鬼为站立伸爪姿态，路西法以羽翼为主，未清楚形成一侧蝠翼。保留已展示的候选与最终选择，未超出 300 积分追加生成。
- 证据：scene-validation.json、final-models-manifest.json、frame-validation.json、video-validation.json、final-qa.json、render-status.json。

最终重新查询旧终端会话时返回：

```text
write_stdin failed: Unknown process id 91656
```

这是已结束会话的查询失败；通过持久化完成状态、Blender 的 render/assemble done 日志及实际成片独立验收确认执行成功，无需重跑。

重新导入当前选定模型（从原始场景另存为最终文件时使用）：

```sh
blender -b library_loop.blend --python-exit-code 2 -P out/build_selected.py
```

最终文件可直接打开或再次渲染；不要为续渲重新运行 Tripo 生成命令。原始生成任务记录与计费证据保留。


## 用户追加：无激光、无天花板灯管的白光预览

用户明确改为原视频的白光循环（中间 → 内侧 → 外侧），并追加去掉蓝色天花板灯管。这是新的视觉版本，按用户新要求替换灯光节奏，保留此前成片和最终场景。

- 新场景：library_loop_white_reference.blend；18 个激光/网格灯管对象隐藏，6 个彩色溢光/蓝色环境灯关闭。
- 只用五盏纯白脚灯；没有补入新的环境光。未亮灯区域接近全黑，暗场只剩标题，是此版本的预期表现。
- 32 帧 / 1.0667 秒一轮：中间、内侧、暗场、外侧、暗场。10 秒场景安排九轮与结尾 12 帧暗场，避免截断内侧亮灯后直接跳回第一帧。
- 模型几何、材质分配、摆放与机位校验保持；飘书、标题与音轨沿用原场景；不调用 Tripo。
- 四个状态帧 1、7、21、31 已按 Cycles 96 / 1920×744 渲染检查，分别耗时 23.22、22.15、19.53、15.83 秒。
- 32 帧周期已完成并重复四次合成预览：128 帧 / 4.2667 秒，1920×744、30 fps，音乐仅铺一条连续音轨。完整新版 300 帧已在用户确认后完成，见下方验收记录。

- 白光预览：out/library_loop_white_reference_preview.mp4，1,129,369 字节；SHA256 6ef457bdff620345c9a9d7a6df0892db361436ee73260833e0d54829306589c0。
- 复用四张检查帧后，其余 28 帧渲染及 PNG 验证耗时 344.57 秒，合成与验证总计 346.85 秒。
- 32 张 PNG 完整性检查通过；实际 MP4 的 1、7、21、31、39 帧解码比对通过（39 对应第二轮的第 7 帧）；48 kHz 双声道音轨可解码且非静音。
- 纯白脚灯脚本与 README 已单独本地提交 02c73fc38e4a3f15bdebd3bb5db1f7909c113844，未推送远端；模型、视频和场景不提交。
- 新版完整 300 帧可复用这 32 帧，按实测估计剩余约 60–90 分钟，不消耗 Tripo 积分。


## 用户确认白光版完整 300 帧

用户在看到 4.27 秒预览和剩余 60–90 分钟估计后回复“确认”。据此已于 2026-11-13T05:09:17.092762+00:00 启动完整白光版 HERO 渲染，复用同一场景已验证的前 32 帧，另外渲染 268 帧。保持 Cycles 96、1920×744、30 fps；不调用 Tripo。

- 最终目标视频：out/library_loop_white_reference.mp4。
- 本轮输出帧：renders/white_reference_full/；原激光版与短预览保留。
- 状态：out/white-reference-full-status.json；日志：out/render-white-reference.log、out/assemble-white-reference.log。
- 本轮已完成，验收结果如下。


## 白光版完整成片验收完成

- 300/300 帧完成：复用已核验的 32 帧，新增 268 帧。连续渲染与帧校验 2881.86 秒，含合成与元数据验证共 2891.91 秒，约 48 分钟。
- 成片：out/library_loop_white_reference.mp4；1920×744、30 fps、300 帧、10.000 秒，H.264 视频与 AAC 双声道音乐；文件 2,516,057 字节。
- SHA256：5b670f1f308bcf95a468f98fa35b476011d494a03f740a0d29ae1997647cdae2。
- 300 张 PNG 的文件集、尺寸、CRC 与像素解压全部通过；实际 MP4 的 1、7、21、150、173、277、300 帧解码比对通过；另目视检查实际解码的 1、150、277、300 帧。
- 102 帧按分镜关闭脚灯，暗场中标题仍可见；无意外空帧。激光、光环、扫描线、天花板灯管及彩色泛光均保持关闭。
- 音轨解码通过，48 kHz、双声道，RMS 0.3811；保留原音乐。
- 本轮没有 Tripo 调用或积分消耗。没有新增运行错误；Blender 6.0 的 API 弃用提示不影响当前 5.3 渲染。
- 源场景 library_loop_white_reference.blend 与用户确认时的 SHA256 一致：89bf55a7b9dccb7b90b74765a6cef102a5581f0d0094374a0ef1313290ef7331。原激光版与短预览保留。
- 本轮状态已置为 complete。证据为 white-reference-full-status.json、white-reference-full-frame-validation.json、white-reference-full-video-validation.json、white-reference-full-qa.json。


## 用户追加：重新设计为金色图书馆灯光

2026-11-13 用户反馈上一版太暗、频闪过强、图书馆不可见，明确授权自行重新设计灯光美术并参考 GitHub VJ loop 项目。此新要求覆盖原始任务书的固定灯光节奏；继续保留已选五尊模型、机位、飘书动作、音乐，关闭激光与蓝色天花板灯管。

已阅读以下真实项目的 README 及实现：
- https://github.com/spite/looper/blob/master/loops/4.js：持续基础照明、周期函数与缓动。
- https://github.com/MatiasDelera/vjlooper/blob/main/core/signals.py：基础值、幅度、相位、循环控制。读取时仓库 SHA aeddf7e7a47ca9530eea0e01820cc9a86b7b8604。
- https://github.com/hfxstudios0001/blender-beat/blob/main/blenderbeat/visual/lighting.py 及 animation/smoothing.py：三点照明和信号平滑。读取时仓库 SHA caf7f53124ed3fbbe6b340aebe86453ac953b446。

没有安装或执行外部项目，新增脚本为本场景单独编写。暖光照亮书架与后墙；中性偏暖主光塑造雕像，少量冷色轮廓光分离背景，保留恒定补光。10 秒一个低幅度循环，主光 ±12%、轮廓光 ±16%、书架光 ±8%，所有灯始终非零。柱子用单独暖灰石材，飘书纸张柔和化；雕像材质保留。标题常亮、下移并加渐暗衬底。

研究与诊断原始错误（均已在聊天告知并继续正常验证）：
- 作者限定的 GitHub 查询失败：`GitHub API error 422: Validation Failed`，错误说明 `The listed users and repositories cannot be searched either because the resources do not exist or you do not have permission to view them.`；改用已确认实际存在的仓库路径读取。
- 诊断脚本对聚光灯读取面光源尺寸失败：`AttributeError: 'SpotLight' object has no attribute 'size'`；改为按灯型读取可选属性后检查通过。试渲本身没有失败。

试光版本保留在 renders/gallery_v1、gallery_v2、gallery_v3；第一版过曝，随后降低整体光能，调整主辅光比和建筑材质，最终检查使用独立目录 renders/gallery_checks。没有用旧版本帧替代新检查。

- 新场景：library_loop_gallery.blend。光照曲线逐帧检查 1–301，首尾闭合，单灯相邻帧最大相对变化约 0.339%；没有黑场或标题掉字动画。
- 新检查帧：1、76、151、226，全部使用 Cycles 96 / Metal / 1920×744。PNG 文件 CRC、尺寸、完整像素解压通过，四张均无纯白截断区域。
- 灯光验证：out/library_loop_gallery-validation.json；实际渲染与像素统计：out/gallery-checks-validation.json；PNG/hash/审批状态：out/gallery-preview-status.json。
- 完整新 300 帧尚未开始；先展示新设计，按用户先前的要求等待新确认。预计 2.5–3 小时，Tripo 新消耗 0。旧两版视频与源场景均保留。

最终新场景 SHA256：df4fcd36c82ecc3e7188bd60ab80744a2019d8dc60536c3fbc91a87aaaca7a5f。四张单帧秒数：1=31.74, 76=28.37, 151=25.93, 226=25.11。

四个阶段已目视核对；联系表 renders/gallery_checks_contact.png。脚本与 README 已本地提交 f189263f4401f9571530532ce13846d32ff76951，未推送。


## 金色图书馆完整渲染获批并启动

用户看到新版关键帧及 2.5–3 小时估计后回复“确认”。本轮按批准的场景 SHA df4fcd36c82ecc3e7188bd60ab80744a2019d8dc60536c3fbc91a87aaaca7a5f 渲染 HERO，Cycles 96、1920×744、300 帧/30 fps，合成原音乐。
启动时间：2026-11-13T07:08:27.353213+00:00。复用已核验的 1、76、151、226 四帧，另外渲染 296 帧；不调用 Tripo。
本轮输出 renders/gallery_full/、out/library_loop_gallery.mp4，状态 out/gallery-full-status.json。管线将先检查完整 PNG，再合成 MP4，并核对解码、音乐、全片亮度及循环接缝；任何失败保留原始报错并停止。


## 金色图书馆完整成片验收完成

- 300/300 帧完成：复用已核验的 1、76、151、226 四帧，新渲染 296 帧。渲染及帧校验 8294.28 秒；含合成、元数据与像素/音轨检查 8319.34 秒，约 2 小时 19 分钟。
- 成片：out/library_loop_gallery.mp4；1920×744、30 fps、300 帧、视频 10.000 秒，H.264 + AAC 双声道音乐，4,292,424 字节。
- 成片 SHA256：2167fa974e8e4b57fba14e5caf63754a85bce984aabf0c795b930b7225a3e6d0。
- 300 张 PNG 的文件集、尺寸、CRC 与完整像素解压通过；实际 MP4 的 1、76、150、151、226、277、300 帧解码比对通过。另目视核对实际 MP4 解码后的 1、150、300 帧，画面符合已确认的金色书架与柔和雕像照明设计。
- 全片无意外黑帧；相邻帧（含 300→1）的平均亮度最大相对变化 0.0537%。首尾转换 RGB RMSE 0.002527，低于普通相邻帧最大值 0.005850，没有额外的循环跳变。
- MP4 音轨可解码且非静音：48 kHz、双声道，RMS 0.381136；保留原音乐。视频/音轨时长的约 0.027 秒差异为既有 AAC 编码/帧长度范围。
- 已确认的场景 SHA256 仍为 df4fcd36c82ecc3e7188bd60ab80744a2019d8dc60536c3fbc91a87aaaca7a5f。没有改动批准后的灯光、材质、模型或机位，没有调用 Tripo、没有新增积分消耗。
- 本轮没有运行失败。完整状态置为 complete；证据：gallery-full-status.json、gallery-full-frame-validation.json、gallery-full-video-validation.json、gallery-full-qa.json。旧激光版与白脚灯版保留。
