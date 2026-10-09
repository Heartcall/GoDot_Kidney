# optimize_for_robot — 机器人本体约束路径优化

在 PathPlanning 的黎曼优化路径（纯几何、不知道机器人是什么）基础上做后处理，
让路径同时满足连续体机器人的曲率极限和贴壁安全距离。只读 PathPlanning 的数据
（`topology_optimized.json`、`cavity.stl`），不写入、不修改 PathPlanning 目录下
任何文件（`riemann_optimizer.py`、`kidney_endoscope_simulator.py` 是同事的代码，
禁止改动，本目录只读复用其中的 `load_mesh`）。

## 目录结构

```
optimize_for_robot/
├── optimize_path_for_robot.py       # 核心：机器人约束优化
├── check_path_curvature.py          # 只读诊断：单独检查一条路径的曲率是否合格
├── export_path_compare_html.py      # 导出：原始 vs 优化后 交互式3D对比图 (plotly)
├── export_path_compare_image.py     # 导出：三视角(正/侧/俯)静态对比图 (matplotlib)
├── export_cavity_path_for_godot.py  # 导出：优化后路径转成 Godot 用的 cavity_path 格式
├── export_point_check_html.py       # 调试用：单点相对网格表面的局部放大检查图
└── data/
    └── organ_1_kidney/
        └── lab_<id>/
            └── topology_robot_smoothed_stone<id>.json   # 优化后的路径 (本目录自己的产出)
```

最终结果落到 `godot_sim/data/organ_1_kidney/lab_<id>/`（跟 `cavity_path_stone<id>.json`
放一起）：`path_compare_stone<id>.html`、`path_compare_stone<id>.png`。

## 一次实验的完整流程

```bash
cd optimize_for_robot
python optimize_path_for_robot.py --lab-id 1 --stone-id 1
python export_path_compare_html.py --lab-id 1 --stone-id 1
python export_path_compare_image.py --lab-id 1 --stone-id 1
python export_cavity_path_for_godot.py --lab-id 1 --stone-id 1
```

## 约束标准

| 项目 | 限值 | 检查方式 |
|---|---|---|
| 主动弯折段（末端65mm，常曲率） | 最小半径 10mm | 逐点三点圆法 (Menger curvature)，严苛、局部敏感 |
| 被动杆身（其余部分，排除末端65mm） | 最小半径 35mm | 30mm 滑动窗口，两端切线夹角换算等效半径 |
| 贴壁安全距离 | 默认 2.5mm | 见下方"贴壁检测"两级方案 |

限值都是用户在开发过程中口头确定的（不是厂商参数表），两种曲率检查方法不同是刻意的：
主动段是被直接驱动的一段，需要对局部尖锐特征敏感；被动段只关心一段长度上的净转向，
逐点法会被重采样留下的锯齿噪声带偏，之前实测产生过一堆没有物理意义的 "~1mm 急弯"。

**主动段曲率判定还叠加了一个最小物理偏移量门槛**（默认 0.2mm，见 `MIN_ACTIVE_DEVIATION_MM`）：
三点法的基线只有2mm，对亚毫米级的数值抖动极其敏感，实测多次出现"算出来半径只有几毫米，
但那个点相对前后邻居连线的实际偏移只有几十到一百多微米"——肉眼完全看不出来、机器人也感知
不到的抖动，不能算真实的急弯。只有半径小**且**实际偏移量达到门槛，才计入超标。

## 优化方法

迭代做 Laplacian 平滑（每个非端点朝相邻两点中点方向挪一点，直接压低局部曲率）+ 30mm 窗口
平滑（每隔若干次迭代做一次，压被动段的大尺度弯曲）+ 贴壁投影（把太靠近壁面的点推回安全
距离外），入口点和结石终点全程锚定不动。不是硬约束求解器，跑完之后用同一套判据重新核实
一遍，如实报告是否真的达标，不假设收敛。

## 贴壁检测：两级方案

单纯用体素化 SDF（`riemann_optimizer.create_sdf_grid`）检测贴壁不够可靠——这个空腔网格在
复杂分支汇合处有自相交缺陷，flood-fill 有时会把本该分开的两个区域误判成连通，且这个问题
与体素分辨率无关（0.25mm 精度下依然复现）。因此：

1. **快速阶段**（300 次迭代主循环内）：仍然用体素 SDF，便宜、每次迭代都能跑，多数情况够用。
2. **鲁棒修正阶段**（快速阶段跑完之后单独一轮）：改用多方向光线投票——从每个点往若干个随机
   方向发射线，数穿过网格表面的次数是奇数(内部)还是偶数(外部)，多数票决定，不会被体素法的
   自相交缺陷骗到。只挪票数不合格的点，每挪一步都重新投票核实，不安全就不采用。最终打印的
   贴壁数字来自这一级，不是快速阶段那个体素近似——保证报告的是真实情况。

如果鲁棒修正阶段跑完还有解决不了的点，会诚实地打印警告，不会假装成功——这通常意味着路径
在这一小段贴着一处真实存在的解剖学窄颈，值得把 `--wall-margin-mm` 调大（目前默认 2.5mm，
调大能明显改善，但会挤压曲率合规的空间，两者需要一起看），或者人工检查这段是否该换个走法。

## 各脚本用法

```bash
# 曲率单独诊断（不改路径，纯只读检查）
python check_path_curvature.py --lab-id 1 --stone-id 1

# 主要参数（都有默认值，一般不用改）
python optimize_path_for_robot.py --lab-id 1 --stone-id 1 \
    --wall-margin-mm 2.5 --iters 300 --alpha 0.15 \
    --window-mm 30 --window-alpha 0.1 --window-every 50
```

## 输出速览

| 产出 | 位置 |
|---|---|
| 优化后路径 | `data/organ_1_kidney/lab_<id>/topology_robot_smoothed_stone<id>.json` |
| 交互式对比图 | `godot_sim/data/organ_1_kidney/lab_<id>/path_compare_stone<id>.html` |
| 三视角静态对比图 | `godot_sim/data/organ_1_kidney/lab_<id>/path_compare_stone<id>.png` |
| Godot 自动巡航路径 | `godot_sim/data/organ_1_kidney/lab_<id>/cavity_path_stone<id>.json` |
