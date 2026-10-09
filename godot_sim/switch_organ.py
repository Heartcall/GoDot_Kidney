"""Switches which organ's mesh + planned path Godot loads.

Godot's main.tscn only ever has ONE kidney_tissue.obj/kidney_cavity.obj
"live" in source_assets/ at a time (the MeshInstance3D's mesh is a plain
ExtResource pointing at that fixed path, not something the engine picks per
organ at runtime), and a separate cavity_path_file setting on the Endoscope
node says which organ/lab/stone's planned path to auto-tour. These two have
to be changed together and kept in sync by hand -- easy to update one and
forget the other, which silently shows one organ's cavity with a totally
different organ's path drawn through it.

This script does both in one step: copies model_asset/<organ>/kidney_tissue.obj
and kidney_cavity.obj over source_assets/'s generic-named files, and rewrites
main.tscn's cavity_path_file line to match.

Usage:
    python switch_organ.py --organ organ_2_kidney --lab-id 1 --stone-id 1
    python switch_organ.py --organ organ_1_kidney --lab-id 2 --stone-id 1
"""
import argparse
import os
import re
import shutil

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_ASSET_DIR = os.path.join(HERE, '..', 'model_asset')
SOURCE_ASSETS_DIR = os.path.join(HERE, 'source_assets')
MAIN_TSCN = os.path.join(HERE, 'main.tscn')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--organ', required=True, help='如 organ_2_kidney')
    ap.add_argument('--lab-id', required=True, help='要跑自动巡径的lab编号')
    ap.add_argument('--stone-id', default='1', help='要跑自动巡径的stone编号，默认1')
    args = ap.parse_args()

    src_dir = os.path.join(MODEL_ASSET_DIR, args.organ)
    tissue_src = os.path.join(src_dir, 'kidney_tissue.obj')
    cavity_src = os.path.join(src_dir, 'kidney_cavity.obj')
    for p in (tissue_src, cavity_src):
        if not os.path.exists(p):
            raise SystemExit(f'未找到 {p} -- 先确认 model_asset/{args.organ}/ 下有转换好的 .obj')

    cavity_path_file = f'res://data/{args.organ}/lab_{args.lab_id}/cavity_path_stone{args.stone_id}.json'
    cavity_path_disk = os.path.join(HERE, 'data', args.organ, f'lab_{args.lab_id}', f'cavity_path_stone{args.stone_id}.json')
    if not os.path.exists(cavity_path_disk):
        print(f'警告: {cavity_path_disk} 还不存在 -- main.tscn会指向一个还没生成的文件，'
              f'自动巡径在游戏里会报"cavity path file not found"，先跑完 pick_stones.py/run_lab.py/export_cavity_path.py 再来')

    tissue_dst = os.path.join(SOURCE_ASSETS_DIR, 'kidney_tissue.obj')
    cavity_dst = os.path.join(SOURCE_ASSETS_DIR, 'kidney_cavity.obj')
    shutil.copyfile(tissue_src, tissue_dst)
    shutil.copyfile(cavity_src, cavity_dst)
    print(f'已复制 {tissue_src} -> {tissue_dst}')
    print(f'已复制 {cavity_src} -> {cavity_dst}')

    with open(MAIN_TSCN, encoding='utf-8') as f:
        tscn = f.read()
    new_tscn, n = re.subn(
        r'cavity_path_file = "res://data/[^"]+"',
        f'cavity_path_file = "{cavity_path_file}"',
        tscn, count=1)
    if n == 0:
        raise SystemExit('main.tscn 里没找到 cavity_path_file 这一行，格式可能变了，需要手动检查')
    with open(MAIN_TSCN, 'w', encoding='utf-8') as f:
        f.write(new_tscn)
    print(f'已更新 main.tscn: cavity_path_file = "{cavity_path_file}"')

    print()
    print(f'现在 Godot 场景会加载 {args.organ} 的mesh + {cavity_path_file} 的路径。')
    print('如果编辑器已经开着，切回编辑器窗口让它检测到 source_assets/ 下文件变化并重新导入；'
          '如果是直接跑打包好的可执行文件，重新启动一次就会读到新文件。')


if __name__ == '__main__':
    main()
