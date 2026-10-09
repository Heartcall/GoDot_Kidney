# PathPlanning — FURS路径规划

从肾脏 / 肾结石 CT 重建的 STL 模型出发，自动提取肾脏骨架、构建从尿道口到各结石的拓扑路径，
模拟内镜回退找最佳观察点，并对路径做平滑优化，最终得到一条可供FURS（输尿管软镜）参考的
碰撞规避路径。全程使用模型原生的毫米坐标系（Godot 场景内部单位约定为 1 unit = 1mm）。

## 目录结构

```
PathPlanning/
├── data/
│   └── organ_1_kidney/       # 按器官分目录，加别的器官就新建 organ_2_xxx/ 这样的同级目录
│       ├── model/            # 该器官共用的空腔 STL（所有实验共用同一份）
│       └── lab_<id>/         # 一次实验：结石 STL + 对应产出放在一起
│           ├── L<n>.stl                  # 结石本体（骨架标签命名）
│           ├── _merged_native.stl        # 合并后的多体结石 STL（run_lab.py 生成）
│           ├── visualization.html        # 交互式 3D 可视化（plotly，run_lab.py 生成）
│           └── result/                   # 骨架/拓扑/内镜模拟/优化路径，四个阶段的产出
├── src/
│   ├── pipeline/            # 主流水线：骨架 → 拓扑 → 内镜模拟 → 路径优化
│   │   ├── kidney_skeleton_extractor.py
│   │   ├── kidney_stone_extractor.py
│   │   ├── kidney_path_topology.py
│   │   ├── kidney_endoscope_simulator.py
│   │   └── riemann_optimizer.py
│   └── visualize/           # 结果查看
│       └── Visualize_Raw.py
├── generate_landmark_poses.py  # 把优化后的路径转成 Godot --photo-set 用的拍摄姿态集
│                                # （虚拟内镜图像库，供实时视觉引导用），见脚本内文档字符串
└── temp_viz/                 # 调试用截图输出（kidney_stone_extractor.py 非交互模式, 按需自动创建）
```

`data/`、`temp_viz/`、`*.stl`、`*.html`、`*.xlsx` 均已在 `.gitignore` 中，不随仓库提交——
仓库本身不自带示例肾脏/结石数据，跑流水线前需要自己准备 `--kidney-stl`/`--stone-stl`
指向的输入文件。

## 环境依赖

Python 3.9+，主要第三方库：

```
numpy trimesh vedo pyvista networkx pandas scipy scikit-image matplotlib pillow openpyxl open3d plotly
```

## 输入数据组织

`data/organ_1_kidney/model/cavity.stl` 是空腔本体，所有实验共用同一份。结石按**所属实验
(lab)**分文件夹，文件名按 `pick_stones.py` 选点时用的**骨架标签**命名（`L<n>` = 端点/叶子，
`B<n>` = 分叉点，标签定义见 `cavity_labeled.png`），不是任意序号：

```
data/organ_1_kidney/
├── model/
│   └── cavity.stl           # 空腔本体（所有实验共用）
└── lab_1/                    # lab_1 这次实验用的结石 + 产出，放一起
    ├── L13.stl                # 端点L13处的结石
    ├── _merged_native.stl
    ├── visualization.html
    └── result/
```

新增一个实验就新建 `lab_<新id>/`，用 `pick_stones.py` 往里面生成任意几个 `<标签>.stl`，
不需要手动指定有几颗——`run_lab.py` 会自动扫描全部数量。

## 一键运行一次实验：`run_lab.py`

```bash
python run_lab.py --lab-id 1
```

做的事情：
1. 扫描 `data/organ_1_kidney/lab_<id>/` 下的全部结石文件，合并成一个临时的多体 STL
   （`_merged_native.stl`）——`kidney_stone_extractor.py` 自己会用连通组件分析把合并后的文件
   重新拆成 N 颗结石，所以合并一个文件传进去，流水线天然就支持多结石，不需要循环调用
2. 依次跑完骨架提取 → 拓扑（用写死的正确入口点，绕开下面提到的 Y-最小点那个坑）→ 内镜回退
   模拟 → SDF 路径优化四个阶段，产出写到 `data/organ_1_kidney/lab_<id>/result/`
3. 生成一个空腔+全部结石+路径的交互式 3D 可视化页面（plotly，鼠标可自由旋转缩放），
   保存到 `data/organ_1_kidney/lab_<id>/visualization.html`

如果需要更细粒度的控制（比如只想单独重跑某一个阶段），按下面"主流水线"里的方式手动逐阶段
调用。

## 主流水线（手动逐阶段调用，run_lab.py 内部就是这样串起来的）

四个阶段按顺序运行，靠磁盘上的 JSON/NPZ 文件衔接（脚本间没有相互 import，除
`kidney_path_topology.py` 复用 `kidney_stone_extractor.py` 的结石提取逻辑）。`kidney_endoscope_
simulator.py`/`riemann_optimizer.py` 需要显式传 `--topology-file`/`--output-dir`、
`--input-json`/`--output-json` 指向 `lab_<id>/result/` 下的对应位置（不传就会落到它们各自
默认的 `result/<case-id>/...`，不是我们要的目录）：

```bash
CASE=lab_1/result
KIDNEY=data/organ_1_kidney/model/cavity.stl
STONE=data/organ_1_kidney/lab_1/L13.stl   # 多颗结石需要先自己合并成一个文件, 见 run_lab.py
OUT=data/organ_1_kidney/lab_1/result

# 1. 从空腔 STL 提取 3D 骨架
python src/pipeline/kidney_skeleton_extractor.py --case-id $CASE --kidney-stl $KIDNEY \
    --output-dir $OUT/skeleton_results
#    -> $OUT/skeleton_results/kidney_skeleton_raw.npz(.json)

# 2. 构建骨架-尿道口-结石拓扑图，求最短路径 (见下方"已知的坑", 手动调用时不要用便捷函数)
python src/pipeline/kidney_path_topology.py --case-id $CASE --kidney-stl $KIDNEY --stone-stl $STONE
#    -> result/$CASE/topology_results/topology_result.json

# 3. 沿路径做内镜回退模拟，找最佳观察点（结石占比 30%），保留树状拓扑
python src/pipeline/kidney_endoscope_simulator.py --case-id $CASE --kidney-stl $KIDNEY --stone-stl $STONE \
    --topology-file $OUT/topology_results/topology_result.json \
    --output-dir $OUT/endoscope_simulation_v2_tree
#    -> $OUT/endoscope_simulation_v2_tree/topology_with_tree_structure.json

# 4. 基于 SDF + 控制点优化做路径平滑，约束路径离腔壁至少 interior-margin (默认0.5mm)
python src/pipeline/riemann_optimizer.py --case-id $CASE --kidney-stl $KIDNEY --stone-stl $STONE \
    --input-json $OUT/endoscope_simulation_v2_tree/topology_with_tree_structure.json \
    --output-json $OUT/topology_optimized/topology_optimized.json \
    --interior-margin 0.5
#    -> $OUT/topology_optimized/topology_optimized.json
```

每个脚本都可以单独覆盖输入 STL/JSON 路径（如 `--kidney-stl`、`--stone-stl`、`--skeleton-file`），
运行 `python <script> --help` 查看全部选项。

`kidney_stone_extractor.py` 也可以单独作为结石 STL 的交互式调试工具运行：

```bash
python src/pipeline/kidney_stone_extractor.py --stone-stl <结石STL路径>
```

### 已知的坑：尿道口自动识别

`kidney_path_topology.py` 的 `build_topology_from_json()` 便捷函数默认把骨架点里 **Y 坐标最小**
的点当作尿道口——这个假设只在原始示例数据的坐标系下成立。换一副模型时不要直接用这个便捷
函数，改成直接构造 `KidneyPathTopology(skeleton_points, skeleton_edges,
urethra_point=<你自己算出的真正入口点>, stone_points=...)`，显式传入正确的入口点坐标。
`run_lab.py` 已经把我们这份共用空腔算好的正确入口点写死在 `ENTRY_POINT_MM` 里，按上面的
方式跑不用再管这个坑；换了别的空腔模型，记得同步更新这个常量。

### `--interior-margin`（riemann_optimizer.py 新增参数）

控制优化后的路径离网格表面至少多远（默认 0.5mm）。如果优化目标网格（`--kidney-stl`）跟
真实渲染/碰撞检测用的网格不是同一份（比如两者之间还隔着一次配准），单纯调大这个值**不能**
弥补两个网格之间的系统性差异——它只影响路径相对 `--kidney-stl` 本身的安全边距，见下方
"多网格配准的经验教训"。

## 多网格配准的经验教训

如果你的空腔模型（cavity）和最终渲染/碰撞检测用的组织模型（tissue）不是同一份原始数据
（比如一个来自 CT 分割、另一个是简化过的可视化资产），两者之间**几乎不可能靠直接配准做到
完全贴合**：

- 直接把 cavity 配准到 tissue（FPFH+RANSAC+ICP）：拟合度可能只有 40%-70%，局部残差可以到
  几十毫米（薄的分支结构、被简化/decimate 掉的部分尤其明显）
- 如果 tissue 是从另一个更高精度模型（比如未简化的原始 CT 网格）衍生出来的，优先把 cavity
  配准到那个原始高精度模型，再复用同一个变换——这样通常能把拟合度提到接近 100%、误差降到
  1-2mm 量级，比直接配准准得多
- 即便配准本身很准，如果目标网格是被 decimate/简化过的低模，局部还是可能出现"简化后网格比
  真实空腔更收窄"的情况，导致贴着空腔中轴的路径在低模网格里露出来——这种情况没法通过调整
  路径的安全边距解决，只能换成未简化的高精度网格，或接受局部有交叉

## 各阶段输出速览

| 阶段 | 输出目录 | 关键文件 |
|---|---|---|
| 骨架提取 | `data/organ_1_kidney/lab_<id>/result/skeleton_results/` | `kidney_skeleton_raw.npz/json`、骨架可视化 PNG |
| 拓扑构建 | `data/organ_1_kidney/lab_<id>/result/topology_results/` | `topology_result.json/xlsx`、路径可视化 PNG |
| 内镜模拟 | `data/organ_1_kidney/lab_<id>/result/endoscope_simulation_v2_tree/` | `topology_with_tree_structure.json`、回退曲线、树状拓扑图、每颗结石采样截图 |
| 路径优化 | `data/organ_1_kidney/lab_<id>/result/topology_optimized/` | `topology_optimized.json` |
| 交互可视化 | `data/organ_1_kidney/lab_<id>/` | `visualization.html`（plotly，run_lab.py 跑完自动生成） |
