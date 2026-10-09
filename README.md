# FURS-NAV — 路径规划与内镜仿真

从肾脏CT重建模型出发，自动规划一条从尿道口到肾结石、满足连续体机器人运动学约束的
碰撞规避路径，并在Godot里搭建一个可交互的内镜仿真环境（含视觉引导算法验证），用于
FURS（输尿管软镜/软性输尿管肾镜取石术）手术路径的离线规划与在线导航研究。

## 整体流程

```
CT DICOM (CT-MI NIAO WAI KE-20260720/)
        │  （人工分割/重建，不在本仓库脚本范围内）
        ▼
  肾脏空腔/组织 STL (model_asset/organ_<N>_kidney/)
        │
        ▼
┌───────────────────────────────────────────────┐
│ godot_sim/PathPlanning/                        │
│   骨架提取 → 拓扑建图(最短路径) → 内镜回退模拟   │
│   → 黎曼(SDF)路径优化                           │
│   纯几何最优，不考虑具体机器人本体               │
└───────────────────────────────────────────────┘
        │  topology_optimized.json
        ▼
┌───────────────────────────────────────────────┐
│ godot_sim/optimize_for_robot/                  │
│   叠加连续体机器人的曲率极限 + 贴壁安全距离约束   │
│   （Laplacian平滑 + 贴壁投影，两级贴壁检测）      │
└───────────────────────────────────────────────┘
        │  topology_robot_smoothed_stone<N>.json
        ▼
┌───────────────────────────────────────────────┐
│ godot_sim/ (Godot 4.7 项目)                     │
│   3D内镜仿真：自动巡径回放规划路径、              │
│   实时视觉引导算法验证、EM/视频数据采集           │
└───────────────────────────────────────────────┘
```

每一步产出都是磁盘上的 JSON/STL 文件，下一步只读取上一步的产出，脚本之间不互相 import
（除 PathPlanning 内部两个阶段复用同一个结石提取模块）。

## 目录结构

```
CT_urology/
├── CT-MI NIAO WAI KE-20260720/   # 原始CT DICOM扫描数据（已gitignore，800M+，含患者信息）
├── model_asset/                  # 各器官的空腔/组织 3D 模型（.stl + Godot用的.obj，已gitignore）
│   └── organ_<N>_kidney/
│       ├── kidney_cavity.stl/.obj   # 空腔（导航用的碰撞体/参考面）
│       └── kidney_tissue.stl/.obj   # 组织外壳（Godot里渲染显示用）
└── godot_sim/                    # Godot 4.7 项目根目录
    ├── PathPlanning/             # 阶段一：纯几何路径规划，详见其 README.md
    ├── optimize_for_robot/       # 阶段二：机器人约束路径优化，详见其 README.md
    ├── data/                     # Godot运行时读取的最终数据：
    │   └── organ_<N>_kidney/lab_<id>/
    │       └── cavity_path_stone<id>.json   # optimize_for_robot 导出的自动巡径路径
    ├── source_assets/            # Godot场景当前"挂载"的mesh（kidney_tissue.obj/kidney_cavity.obj）
    │                              # 同一时刻只有一个器官的mesh在这里，靠 switch_organ.py 切换
    ├── scripts/                  # Godot GDScript：内镜控制器、腔体碰撞、引导线叠加层等
    ├── main.tscn                 # 主场景（内镜仿真入口）
    ├── switch_organ.py           # 切换当前加载的器官/lab（同时换mesh+路径，两者需保持一致）
    ├── captures/                 # 仿真自动拍摄的参考图像库（已gitignore，可重新生成）
    ├── recordings/               # Godot Movie Maker录的演示视频（已gitignore）
    └── analysis/                 # 生成的分析产出（已gitignore，可重新生成）
```

## 快速开始

**1. 跑一次完整的路径规划实验**（以 organ_1_kidney/lab_1 为例，前提是已经把结石 STL
放进了 `PathPlanning/data/organ_1_kidney/lab_1/`，见 `PathPlanning/README.md`）：

```bash
cd godot_sim/PathPlanning
python run_lab.py --lab-id 1

cd ../optimize_for_robot
python optimize_path_for_robot.py --lab-id 1 --stone-id 1
python export_cavity_path_for_godot.py --lab-id 1 --stone-id 1
```

**2. 在Godot里加载这次实验的结果：**

```bash
cd godot_sim
python switch_organ.py --organ organ_1_kidney --lab-id 1 --stone-id 1
```

用 Godot 编辑器（或命令行 `godot --path godot_sim`）打开 `main.tscn` 运行即可。

## 详细文档

- 路径规划四阶段流水线（骨架提取/拓扑/内镜模拟/黎曼优化）、输入数据组织、已知坑：
  见 [`godot_sim/PathPlanning/README.md`](godot_sim/PathPlanning/README.md)
- 机器人本体约束优化（曲率限值、贴壁检测两级方案）、各导出脚本用法：
  见 [`godot_sim/optimize_for_robot/README.md`](godot_sim/optimize_for_robot/README.md)

## 环境依赖

- **Python 3.9+**（PathPlanning / optimize_for_robot 两套流水线）：
  `numpy trimesh vedo pyvista networkx pandas scipy scikit-image matplotlib pillow openpyxl open3d plotly`
- **Godot 4.7**（`config/features` 里声明的引擎版本）

## 关于 `.gitignore`

原始CT数据、3D模型资产（几百MB量级二进制）、仿真运行时可重新生成的产出（captures/
analysis/recordings）、训练checkpoint等都已排除在版本控制之外——这些要么体积大、要么
可以从流水线重新跑出来，不需要进 git 历史。具体规则见仓库根目录 `.gitignore`。
