"""Freeze approved P1 inputs; rebuild P2 assets WITHOUT a deformation solver.

Initial export: --from-approved. Subsequent rebuilds use tracked frozen arrays.
All six authority hashes are checked before any output is written.
"""
import argparse
import hashlib
import json
import shutil
import struct
import subprocess
from pathlib import Path

import numpy as np

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
ROOT = PROJECT / 'deformation/p2'
RUNTIME = ROOT / 'runtime'
DIAG = PROJECT / 'analysis/irrigation_baseline/p2'
R2 = PROJECT / 'analysis/irrigation_baseline/p15_r2'
R1 = PROJECT / 'analysis/irrigation_baseline/p15_contact_research'
ORIGIN = np.array([16., 16., -81.])
AUTHORITY = {
    'cavity_reference_vertices': 'f137add4c401fe63851565f913a93968c9b11e18e630722ed42a21b4d0842fa1',
    'cavity_faces': 'dbf4771365f42398f329100e695dc8580f8c038c557c671c02724bff45b29c3d',
    'cavity_displacement': 'fbe95cfeaf8b77d80c5aa850618ad8ce8439c8ef770719b1f9a1f1789b050573',
    'tissue_reference_vertices': '63ce22d71be21c2a1266933aac2112ab7c66bcd887312f81e1d7d87c4f9ecb20',
    'tissue_faces': '532034f649eac73d2c28ecba5f0097ba04b79164fea3e385de5518c098cc3a05',
    'tissue_displacement': 'bcef3bda21aa3621547a80f8d7902c7506fc638cd8c18fe6a8c8c5516491eaec',
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + '\n', encoding='utf8')


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def approved_path(key):
    mesh, item = key.split('_', 1)
    base = PROJECT / 'deformation/full_cavity/field' if mesh == 'cavity' else R2 / 'candidate'
    return base / (item + '.npy')


def verify_sources(from_approved=False):
    paths = {k: approved_path(k) if from_approved else RUNTIME / (k + '.npy') for k in AUTHORITY}
    for key, path in paths.items():
        if not path.is_file() or sha(path) != AUTHORITY[key]:
            raise ValueError(f'STOP: missing or changed accepted input: {path}')
    arrays = {k: np.load(p, allow_pickle=False) for k, p in paths.items()}
    for mesh, n, m in [('cavity', 25024, 50044), ('tissue', 155904, 311844)]:
        v, f, d = [arrays[mesh + '_' + item] for item in ('reference_vertices', 'faces', 'displacement')]
        if v.shape != (n, 3) or f.shape != (m, 3) or d.shape != v.shape:
            raise ValueError('STOP: invalid array shape')
        if not np.isfinite(v).all() or not np.isfinite(d).all() or f.min() < 0 or f.max() >= n:
            raise ValueError('STOP: invalid accepted geometry')
    return paths, arrays


def protected_snapshot():
    DIAG.mkdir(parents=True, exist_ok=True)
    target = DIAG / 'protected_before.json'
    if target.exists():
        return
    names = subprocess.check_output(['git', 'ls-files', '-z'], cwd=REPO).decode('utf8').split('\0')
    paths = {REPO / name for name in names if name and (REPO / name).is_file()}
    for base in (PROJECT / 'deformation', PROJECT / 'analysis/irrigation_baseline'):
        for path in base.rglob('*'):
            if path.is_file() and path.suffix in ('.npy', '.bin', '.json', '.csv', '.md', '.png'):
                if ROOT not in path.parents and DIAG not in path.parents:
                    paths.add(path)
    write_json(target, {p.relative_to(REPO).as_posix(): sha(p) for p in sorted(paths)})


def freeze_evidence():
    evidence = ROOT / 'evidence'
    evidence.mkdir(exist_ok=True)
    # Preserve historical wording. New accepted_inputs records subsequent human acceptance.
    for src, name in [(R2 / 'quality_report.json', 'r2_quality_report.json'),
                      (R2 / 'godot_runtime_validation.json', 'r2_runtime_validation.json')]:
        shutil.copyfile(src, evidence / name)
    audit = PROJECT / 'deformation/p15_audit'
    extras = {
        'port_fixed_masks': PROJECT / 'deformation/p1_masks/port_fixed_masks.npy',
        'coincident_mask': R1 / 'coincident_mask.npy',
        'coincident_cavity_vertex': R1 / 'coincident_cavity_vertex.npy',
        'remote_anchors': R1 / 'remote_anchors.npy',
        'contact_pairs': audit / 'cross_contact_pairs.npy',
        'contact_sample_points': R1 / 'original_contact_sample_points.npy',
    }
    for name, path in extras.items():
        shutil.copyfile(path, evidence / (name + '.npy'))
    # Hash actual approved R2 outputs for a direct new-runtime identity proof.
    comparisons = {}
    for mesh in ('cavity', 'tissue'):
        n, m = (25024, 50044) if mesh == 'cavity' else (155904, 311844)
        for tag in (0, 25, 50, 75, 100):
            raw = (R2 / f'godot_validation/after_{mesh}_u{tag:03}.bin').read_bytes()
            if len(raw) != 24*n + 12*m:
                raise ValueError('Invalid approved runtime snapshot')
            comparisons[f'{mesh}_u{tag:03}'] = {
                'positions_sha256': hashlib.sha256(raw[:12*n]).hexdigest(),
                'indices_sha256': hashlib.sha256(raw[24*n:]).hexdigest(),
            }
    write_json(evidence / 'r2_actual_array_hashes.json', comparisons)


def build(from_approved=False):
    paths, arrays = verify_sources(from_approved)  # MUST precede all mutations.
    if from_approved:
        if (ROOT / 'accepted_inputs.json').exists():
            raise ValueError('Already frozen: rebuild from tracked resources without --from-approved')
        # Verify evidence exists before freezing anything.
        for path in (R2/'quality_report.json', R2/'godot_runtime_validation.json'):
            if not path.is_file():
                raise ValueError('STOP: accepted validation evidence missing')
        protected_snapshot()
        RUNTIME.mkdir(parents=True, exist_ok=True)
        for key, src in paths.items():
            shutil.copyfile(src, RUNTIME / (key + '.npy'))
        freeze_evidence()
    else:
        manifest = read_json(ROOT / 'accepted_inputs.json')
        for name, digest in manifest['evidence_sha256'].items():
            if sha(ROOT / 'evidence' / name) != digest:
                raise ValueError('STOP: frozen validation evidence changed')
    binaries = {}
    for mesh in ('cavity', 'tissue'):
        v, f, d = [arrays[mesh+'_'+item] for item in ('reference_vertices', 'faces', 'displacement')]
        raw = b'P2DG0001' + struct.pack('<II', len(v), len(f))
        raw += np.asarray(v-ORIGIN, dtype='<f4').tobytes()
        raw += np.asarray(d, dtype='<f4').tobytes()
        raw += np.asarray(f[:, ::-1], dtype='<i4').tobytes()
        path = RUNTIME / (mesh + '.bin')
        path.write_bytes(raw)
        binaries[mesh] = {'path': 'runtime/'+path.name, 'sha256': sha(path), 'vertices': len(v), 'triangles': len(f)}
    manifest = {
        'schema': 'P2_ACCEPTED_INPUTS_V1', 'version': 'p2.1-p2.2-v1', 'unit': 'mm',
        'human_acceptance': {'date': '2026-10-14', 'stage': 'P1.5-R2', 'status': 'USER_ACCEPTED_ENGINEERING_GEOMETRY',
                             'source': 'User explicitly accepted synchronous geometry, three states, slider, F01/F02 and five-level engineering checks.'},
        'authority': 'docs/kidney_irrigation_p2_guide.md section 2',
        'origin_mm': ORIGIN.tolist(), 'formula': 'reference + u * accepted_displacement',
        'float32_formula': 'float32(reference-origin) + float32(u)*float32(displacement)',
        'cavity_maximum_displacement_mm': .2,
        'arrays': {k: {'source': approved_path(k).relative_to(REPO).as_posix(),
                       'runtime': 'runtime/'+k+'.npy', 'sha256': AUTHORITY[k], 'shape': list(arrays[k].shape),
                       'dtype': str(arrays[k].dtype)} for k in AUTHORITY},
        'binaries': binaries,
        'evidence_sha256': {p.name: sha(p) for p in sorted((ROOT/'evidence').iterdir()) if p.is_file()},
        'limits': ['No physiological calibration, true wall-thickness validation or confirmed F03/F04 anatomy.',
                   'Five-level finite contact checks do not certify collision freedom over all continuous u.',
                   'Runtime reads only P2 versioned assets, never analysis cache or R1 displacement.'],
    }
    write_json(ROOT/'accepted_inputs.json', manifest)
    verify_sources(False)
    print(json.dumps({'status': 'FROZEN_INPUTS_VERIFIED', 'six_authority_hashes_exact': True,
                      'runtime_binary_sha256': {k: v['sha256'] for k, v in binaries.items()}}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--from-approved', action='store_true')
    build(parser.parse_args().from_approved)
