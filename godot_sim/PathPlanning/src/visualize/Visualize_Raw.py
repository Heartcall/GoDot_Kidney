#!/usr/bin/env python3
"""
Visualize kidney parenchyma, renal cavity, and kidney stone from STL files.
Parenchyma (solid kidney tissue = shell - cavity): semi-transparent red (alpha=0.15)
Cavity (renal pelvis / collecting system): semi-transparent cyan (alpha=0.25)
Stone: solid yellow
No coordinate axes displayed.
"""

import sys
from vedo import Mesh, Plotter

# === CONFIGURATION ===
stone_stl_file = "kidney/KidneyStone_1.stl"          # required
cavity_stl_file = "kidney/kidney.stl"                # optional (renal cavity)
parenchyma_stl_file = "kidney/kidney_parenchyma.stl" # optional (solid kidney tissue)
# =====================

def load_optional(path, color, alpha, label):
    try:
        mesh = Mesh(path)
        mesh.color(color).alpha(alpha)
        print(f"{label} loaded.")
        return mesh
    except FileNotFoundError:
        print(f"Warning: {label} file not found at {path}", file=sys.stderr)
    except Exception as e:
        print(f"Error loading {label}: {e}", file=sys.stderr)
    return None

def main(stone_stl=stone_stl_file, cavity_stl=cavity_stl_file, parenchyma_stl=parenchyma_stl_file):
    actors = []

    parenchyma = load_optional(parenchyma_stl, "red", 0.15, "Parenchyma")
    if parenchyma is not None:
        actors.append(parenchyma)

    cavity = load_optional(cavity_stl, "cyan", 0.25, "Cavity")
    if cavity is not None:
        actors.append(cavity)

    # Load stone (mandatory)
    try:
        stone = Mesh(stone_stl)
        stone.color("yellow").alpha(1.0)  # opaque
        actors.append(stone)
        print("Stone loaded.")
    except FileNotFoundError:
        print(f"Error: Stone file not found at {stone_stl}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error loading stone: {e}", file=sys.stderr)
        sys.exit(1)

    # Display scene without axes
    if actors:
        plt = Plotter(title="Kidney parenchyma (red), cavity (cyan), and stone (yellow)",
                       bg="white")

        def make_toggle(mesh, label):
            def toggle(_obj, _ename):
                if mesh.actor.GetVisibility():
                    mesh.off()
                else:
                    mesh.on()
                buttons[label].switch()
            return toggle

        # (mesh, label, button color) for every optional/toggleable layer, from bottom up
        toggle_specs = [
            (stone, "Stone", "yellow4"),
            (cavity, "Cavity", "cyan4"),
            (parenchyma, "Parenchyma", "red4"),
        ]

        buttons = {}
        y = 0.05
        for mesh, label, color in toggle_specs:
            if mesh is None:
                continue
            buttons[label] = plt.add_button(
                make_toggle(mesh, label),
                states=[f"Hide {label}", f"Show {label}"],
                pos=(0.85, y),
                size=24,
                bc=[color, "grey"],
            )
            y += 0.07

        plt.show(actors, axes=0, interactive=True)
    else:
        print("No objects to display.")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stone-stl", default=stone_stl_file, help="Required stone STL")
    parser.add_argument("--cavity-stl", default=cavity_stl_file, help="Optional renal cavity STL")
    parser.add_argument("--parenchyma-stl", default=parenchyma_stl_file, help="Optional kidney parenchyma STL")
    args = parser.parse_args()

    main(stone_stl=args.stone_stl, cavity_stl=args.cavity_stl, parenchyma_stl=args.parenchyma_stl)