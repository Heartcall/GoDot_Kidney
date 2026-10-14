# P2.1 / P2.2 versioned geometry resources

`accepted_inputs.json` records the user's 2026-10-14 acceptance and all six
authoritative input hashes from `docs/kidney_irrigation_p2_guide.md` section 2.
The six `runtime/*.npy` files are byte-for-byte copies of the accepted arrays,
including the R2 tissue candidate previously stored in ignored analysis cache.
Do not edit these inputs or substitute the R1 tissue field.

The preview reads only this manifest and `runtime/cavity.bin`, `runtime/tissue.bin`.
It does not read original OBJ, analysis cache, or historical preview binaries.
Keep this entire directory with the P2 scripts and scene when committing changes.

Binary version `P2DG0001`, little endian:

1. 8-byte ASCII magic, uint32 vertex count, uint32 triangle count.
2. N × 3 float32 centered reference coordinates, `(reference-[16,16,-81])` mm.
3. N × 3 float32 accepted displacement, mm.
4. M × 3 int32 triangle indices, reversed from source OBJ order for Godot.

Geometry is always rebuilt as `reference32 + float32(u)*displacement32`;
source float64 arrays and original face order remain available in the NPY files.
Normals are recomputed from current geometry. No vertex/index remapping occurs.

Rebuild using only these frozen assets (no ignored cache required):

```powershell
& 'E:/Apps/Conda/miniconda3/envs/FURS/python.exe' godot_sim/tools/p2/prepare_runtime.py
```

`--from-approved` is only the initial one-time freeze; it fails if the input
manifest already exists. Neither mode contains a mapping solver.

`evidence/` preserves accepted R2 quality and runtime results plus constraint
arrays, with hashes in the manifest. Historical “pending” wording remains in
copied historical reports; the subsequent user acceptance is in the new manifest.
`verification/` contains the new P2 execution evidence, not geometry inputs.

Current engineering limits remain: no true pressure/flow calibration, no proven
F03/F04 anatomical assignment or true wall thickness; five-level contact scans
do not certify continuous collision freedom. CPU mesh updates remain too slow
for a demonstrated stable 30 fps. See the P2 result document before acceptance.
