# V-Demo：人工 v3 内镜动态肾腔视频

交付日期：2026-10-16。已完成短样片、完整录制及普通实时预览。仅供视觉展示，不增加动态碰撞或物理仿真。

## 交付文件

以下路径均相对于仓库根目录 `E:/Study/双翌老师组/Simulator/FURS-NAV-main`。

| 文件 | 用途 |
|---|---|
| `godot_sim/recordings/endoscope_v3_final.mp4` | 最终视频，1920×1080、30 FPS、H.264、BT.709、无音轨 |
| `godot_sim/recordings/endoscope_v3_sample2.mp4` | 先行验证的约 2 秒短样片，同样覆盖完整收缩—扩张—收缩周期 |
| `godot_sim/recordings/endoscope_v3_final.avi` | Godot Movie Maker 原始录制，MJPEG |
| `godot_sim/visual_demo_endoscope_video.tscn` | F6 独立运行场景 |
| `godot_sim/visual_demo/scripts/endoscope_video.gd` | 统一时钟、实时 Morph Targets、灯光、录制结束控制 |
| `godot_sim/visual_demo/scripts/endoscope_video_path.gd` | 继承原控制器，复用路径采样和姿态计算 |
| `godot_sim/visual_demo/assets/kidney_manual_v3.glb` | 当前人工 v3 导出的正式 GLB，附 `.import` 导入设置 |
| `visual_demo/tools/record_endoscope.ps1` | 一键 Movie Maker 录制并转换 MP4 |
| `visual_demo/endoscope_v1/reports/` | 模型检查、运行日志、几何验证、视频验证、保护文件校验 |
| `godot_sim/recordings/endoscope_v3_final_frames.csv` | 241 帧的时间、形变权重、原路线弧长和相机姿态 |
| `godot_sim/recordings/endoscope_v3_final_contact_sheet.jpg` | 从最终 MP4 解码的九帧验收图；字幕仅在验收图中 |

## A. F6 实时预览

1. 用 Godot 4.7 打开原 `godot_sim/project.godot`，等待资产导入完成。
2. 打开 `visual_demo_endoscope_video.tscn`，关闭编辑器的 Movie Maker 按钮，按 F6。
3. 内镜自动沿选定短段前进，同时腔壁实时变化。默认 8 秒后重播；重播时路线会重置到短段起点。
4. 按 F8 结束预览。选中场景根节点，可在检查器中修改 `Duration Seconds`、`Video Fps`、`Path Start Progress`、`Path End Progress`、`Preview Loop`。

场景复用原 `main.tscn` 的相机 FOV=90°、相机滚转、镜头畸变效果，以及相机前方的灯光结构。仅在独立场景的运行实例中移除静态组织、碰撞体和调试覆盖层，关闭近景虚化，设置粉红色双面湿润材质及柔和光照。画面里的腔壁就是正式 GLB 中的 `KidneyCavity`，没有 TissueReference 遮挡。

## B. 1080p Movie Maker 录制

在仓库根目录打开 PowerShell：

```powershell
& ./visual_demo/tools/record_endoscope.ps1
```

脚本执行 Godot Movie Maker 固定帧率录制，正常退出后使用 FFmpeg 转为 MP4。默认生成 `godot_sim/recordings/endoscope_v3_final.avi` 和 `.mp4`；同名文件会覆盖，可用 `-Name` 保留不同版本。

先录短样片：

```powershell
& ./visual_demo/tools/record_endoscope.ps1 -Duration 2 -Fps 30 -Name endoscope_v3_short
```

自定义时长和原路线弧长进度（0 到 1）：

```powershell
& ./visual_demo/tools/record_endoscope.ps1 -Duration 8 -Fps 30 -Start 0.5778149846 -End 0.6933779815 -Name endoscope_v3_take2
```

`Duration × Fps` 应为偶数整数，使第一帧、半周期最大扩张帧和末帧都准确采样。默认 8×30=240 个时间间隔，连同起点共 **241 帧**，播放时长 **8.0333 秒**。这与已提供的 Blender `0001-0241.mp4` 的 1080p、30 FPS、约 8.03 秒一致。动画时间为 0–8 秒，末帧占据最后一个播放帧时长。

Godot 4.7 在 post-draw 请求正常退出后，还会给 AVI 写入一帧结尾重复画面，因此原始 AVI 为 242 帧。转换保留 0–240 共 241 帧；已用渲染截图与 AVI 帧对应核验，**不删除起点，不丢失结束收缩态**。MP4 设置 H.264、yuv420p、BT.709 limited range、30 FPS、faststart，与 Blender 视频格式对齐，可直接放入剪辑时间线拼接。

录制脚本临时创建 `godot_sim/override.cfg`，只在 Movie Maker 启动时设定 1920×1080；结束自动清除，不修改 `project.godot`。若已有同名配置，脚本会保留它并停止，避免覆盖。不要并行启动两次此录制脚本。仅在编辑器中直接开启 Movie Maker/F6，原项目尺寸可能仍为 1422×1066；交付的 1080p 录制方式应使用上述脚本。

默认程序位置：

- Godot：`E:/Apps/Godot/Godot_v4.7-stable/Godot_v4.7-stable_win64_console.exe`
- FFmpeg：`visual_demo/endoscope_v1/vendor/imageio_ffmpeg/binaries/ffmpeg-win-x86_64-v7.1.exe`

更换机器后可传 `-Godot '完整路径' -Ffmpeg '完整路径'`。FFmpeg 来自本地工具目录中的 `imageio-ffmpeg 0.6.0` 包，不要求全局安装。录制所用 Movie Maker 方法参考 [Godot 官方中文说明](https://docs.godotengine.org/zh-cn/4.x/tutorials/animation/creating_movies.html)。

## 形变与坐标约定

人工输入是 `visual_demo/blender/kidney_manual_v3.blend`，SHA-256：

```text
a450e8f639d7d647ff8238a09cff2f20458beb4f8a4229b72ea6e425e6802d69
```

实际打开 Blender 5.2.2 检查并导出；人工工程中有 `Basis / Contracted / Expanded`，25024 顶点、50044 三角形，物体矩阵为单位阵。导出脚本只在临时内存会话中关闭关键帧动画并将权重归零，不保存 `.blend`。GLB 的基础顶点代表 Basis，两个 Morph Targets 分别是 Contracted、Expanded；Godot 中也是两个可驱动权重，不把 Basis 当成第三个权重。

统一参数：

```text
u = t / duration
s = 0.2 - 0.8*cos(2*pi*u)
Contracted = max(-s, 0)
Expanded   = max( s, 0)
```

0 秒：`(0.6,0)`；4 秒：`(0,1)`；8 秒：`(0.6,0)`。运行日志中的 0.6000000238 是 32 位浮点对 0.6 的表示。Reference 在约 1.6783、6.3217 秒经过，参数速度非零；没有中间停顿。仅周期两端和最大扩张处自然减速。

原路线和原控制器保持 RAS 毫米坐标。GLB 坐标为 `((R-16), (S+81), -(A-16))*0.001`。独立场景把 GLB 还原到原 RAS 毫米世界：

```text
R = 1000*GLB.x + 16
A = -1000*GLB.z + 16
S = 1000*GLB.y - 81
```

因此不需要重写路线或改变原姿态算法。实际 Godot 烘焙后的三态顶点已与人工 Shape Keys 比较，最大误差低于 0.00001 mm。内镜位置由同一时钟给出的弧长进度控制；姿态继续调用原控制器的分叉周转、巡航朝向和限速插值方法，并以原项目的 240 Hz 子步更新。起始姿态通过在画面开始前重放原控制器从路径起点到选段起点的朝向历史得到。

## 验收结果与范围

测试环境：Godot 4.7 stable / Forward+ / Vulkan / NVIDIA GeForce RTX 4070 Ti。普通实时预览和固定帧率录制均已实际运行。

选用原路线 **50–60 mm**，总路线约 **86.532889 mm**，对应起止进度 **0.5778149846–0.6933779815**。这段在分叉调整区之前，朝向变化平缓，能看到腔壁运动。原控制器日志把长度标作 `m` 是原有日志文字错误；此数据实际为 mm，未修改原脚本。

| 检查 | 实际结果 |
|---|---|
| 当前人工 v3 文件与正式导出 | 已核验 SHA-256，未使用 DRAFT GLB |
| 原路径上的 241 个相机位置，固定 Contracted=0.6 | 全部在腔内，最小壁面距离 1.66217 mm |
| 同一组相机位置，固定 Reference | 全部在腔内，最小距离 2.51829 mm |
| 同一组相机位置，固定 Expanded=1 | 全部在腔内，最小距离 2.56959 mm |
| 每一实际帧的动态腔壁和对应相机 | 241/241 在腔内，最小距离 1.66217 mm |
| 相机位置偏离权威路径 | 最大约 0.0000064 mm，浮点误差范围 |
| 相邻帧相机旋转 | 最大约 0.117°，无异常翻转 |
| 实际首、中、末权重 | (0.6,0) → (0,1) → (0.6,0) |
| 最终视频 | H.264、1080p、30 FPS、241 帧，已全帧解码检查 |
| 可视画面 | 动态粉红腔壁、柔和高光；检查采样帧及帧间变化，无明显穿墙或严重闪烁 |
| 受保护源文件 | 2753 个校验均未变化，包含人工工程、原场景/控制器和权威数据 |

此距离检查针对视觉镜头光心，不代表实体内镜半径或碰撞物理认证。路径后段约 70–85 mm 在收缩态扫描中发现部分点越出腔壁，因此未选用。修改起止进度后应重新检查对应片段，不可推断整条路线都安全；本次未修改人工 Shape Keys 或原路径来掩盖这一问题。

主要证据：

- `visual_demo/endoscope_v1/reports/manual_v3_inspection.json`、`blender_export.log`：人工工程与正式导出。
- `visual_demo/endoscope_v1/reports/godot_import.log`：正式资产导入。
- `visual_demo/endoscope_v1/reports/endoscope_v3_final.log`、`preview.log`：真实运行及正常退出。
- `visual_demo/endoscope_v1/reports/final_geometry_validation.json`：三态、动态逐帧、坐标和姿态验证。
- `visual_demo/endoscope_v1/reports/endoscope_v3_final_video_validation.json`：MP4 全帧解码、帧对应关系和文件哈希。报告中的 `source_size` 是视频原始 1920×1080，`size=480×270` 仅为验证时解码缩略尺寸。
- `visual_demo/endoscope_v1/reports/protected_after.json`：受保护文件零改动。

需要复验时，在仓库根目录运行：

```powershell
& E:/Apps/Conda/miniconda3/envs/FURS/python.exe visual_demo/tools/endo_validate_final.py
& E:/Apps/Conda/miniconda3/envs/FURS/python.exe visual_demo/tools/endo_video_delivery.py endoscope_v3_final
```

后者重新从 AVI 生成 MP4 并验证，几何验证需要该环境中的 NumPy、SciPy、VTK；正常预览和录制不依赖这些几何分析库。
