"""Read-only geometry inputs; isolated full-route visual demonstration outputs."""
from pathlib import Path
import sys, json, hashlib
import numpy as np
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray, vtk_to_numpy
from scipy.interpolate import PchipInterpolator

REPO=Path(__file__).resolve().parents[2]
ROOT=REPO/'visual_demo/full_route_v6'
PROJECT=REPO/'godot_sim'
SOURCE=PROJECT/'data/organ_2_kidney/lab_6/cavity_path_stone1.json'
SHAPES=REPO/'visual_demo/endoscope_v1/data/manual_v3_shapes_RAS_mm.npz'
BLEND=REPO/'visual_demo/blender/kidney_manual_v3.blend'
GLB=PROJECT/'visual_demo/assets/kidney_manual_v3.glb'
DEMO_PATH=PROJECT/'visual_demo/data/full_route_c04.json'
for folder in ['reports','data','preview']: (ROOT/folder).mkdir(parents=True,exist_ok=True)

def read(path): return json.loads(Path(path).read_text(encoding='utf8'))
def write(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf8')
def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def protect(initial=False):
    manifest=ROOT/'reports/protected_before.json'
    if initial and not manifest.exists():
        old=read(REPO/'visual_demo/endoscope_v1/reports/protected_before.json')
        names=set(old)|{str(p.relative_to(REPO)).replace('\\','/') for p in [BLEND,GLB,SHAPES,SOURCE,PROJECT/'main.tscn',PROJECT/'scripts/endoscope_controller.gd',PROJECT/'project.godot']}
        write(manifest,{name:sha(REPO/name) for name in sorted(names)})
    before=read(manifest)
    changed=[name for name,digest in before.items() if sha(REPO/name)!=digest]
    write(ROOT/'reports/protected_after.json',{'checked':len(before),'changed':changed})
    if changed:raise RuntimeError('Protected inputs changed: '+str(changed))

def lengths(points):return np.r_[0,np.cumsum(np.linalg.norm(np.diff(points,axis=0),axis=1))]
def sample(points,offsets):
    arc=lengths(points)
    return np.column_stack([np.interp(offsets,arc,points[:,i]) for i in range(3)])
def normalized(v):return v/np.maximum(np.linalg.norm(v,axis=-1,keepdims=True),1e-12)

class Geometry:
    def __init__(self):
        audit=read(REPO/'visual_demo/endoscope_v1/reports/manual_v3_inspection.json')
        assert sha(BLEND)==audit['source_blend_sha256'] and sha(GLB)==audit['GLB_sha256'], 'Artist input has changed: re-audit before reuse'
        data=np.load(SHAPES);self.basis=data['Basis'];self.dc=data['Contracted']-self.basis;self.de=data['Expanded']-self.basis;self.faces=data['faces'];self.cache={}
        self.max_motion={'contracted':float(np.linalg.norm(self.dc,axis=1).max()),'expanded':float(np.linalg.norm(self.de,axis=1).max())}
    def vertices(self,state):return self.basis+max(-state,0)*self.dc+max(state,0)*self.de
    def mesh(self,state):
        points=vtk.vtkPoints();points.SetData(numpy_to_vtk(self.vertices(state),deep=True))
        cells=vtk.vtkCellArray();cells.SetCells(len(self.faces),numpy_to_vtkIdTypeArray(np.column_stack([np.full(len(self.faces),3),self.faces]).ravel().astype(np.int64),deep=True))
        mesh=vtk.vtkPolyData();mesh.SetPoints(points);mesh.SetPolys(cells);return mesh
    def field(self,state):
        state=round(float(state),9)
        if state not in self.cache:
            obj=vtk.vtkImplicitPolyDataDistance();obj.SetInput(self.mesh(state));self.cache[state]=obj
        return self.cache[state]
    def clearance(self,points,state):
        field=self.field(state)
        points=np.ascontiguousarray(np.atleast_2d(points),dtype=float)
        output=vtk.vtkDoubleArray();output.SetNumberOfTuples(len(points))
        field.FunctionValue(numpy_to_vtk(points,deep=True),output)
        return -vtk_to_numpy(output).copy()
    def worst(self,points,states=(-.4,0.,1.)):
        return np.min([self.clearance(points,s) for s in states],axis=0)
    def enclosed(self,points,state):
        pp=vtk.vtkPoints();pp.SetData(numpy_to_vtk(np.asarray(points),deep=True));probe=vtk.vtkPolyData();probe.SetPoints(pp)
        enclosed=vtk.vtkSelectEnclosedPoints();enclosed.SetSurfaceData(self.mesh(state));enclosed.SetInputData(probe);enclosed.SetTolerance(1e-8);enclosed.Update()
        return np.array([bool(enclosed.IsInside(i)) for i in range(len(points))])

def initial_scan():
    protect(True);g=Geometry();data=read(SOURCE);pts=np.array(data['points']);arc=lengths(pts)
    offsets=np.linspace(0,arc[-1],int(np.ceil(arc[-1]/.1))+1);p=sample(pts,offsets)
    states=np.round(np.arange(-.4,1.0001,.1),8)
    clearance=np.array([g.clearance(p,s) for s in states])
    import trimesh
    mesh=trimesh.Trimesh(g.basis,g.faces,process=False)
    report={'source_hashes':{'blend':sha(BLEND),'glb':sha(GLB),'path':sha(SOURCE),'shapes':sha(SHAPES)},'topology':{'watertight':bool(mesh.is_watertight),'consistent_winding':bool(mesh.is_winding_consistent),'volume_mm3':float(mesh.volume),'vertices':len(g.basis),'faces':len(g.faces)},'max_vertex_displacement_mm':g.max_motion,'original_length_mm':float(arc[-1]),'start':pts[0].tolist(),'end':pts[-1].tolist(),'states':states.tolist(),'offsets_mm':offsets.tolist(),'signed_clearance_mm':clearance.tolist(),'junctions_mm':data['junctions'],'state_summary':[]}
    for i,s in enumerate(states):
        mask=clearance[i]<0
        summary={'s':float(s),'min_mm':float(clearance[i].min()),'outside_count':int(mask.sum()),'outside_original_offsets_mm':offsets[mask].tolist(),'start_mm':float(clearance[i,0]),'end_mm':float(clearance[i,-1])}
        report['state_summary'].append(summary);print(summary,flush=True)
    for s in [-.4,0,1]:assert np.array_equal(g.clearance(p,s)>0,g.enclosed(p,s)), 'Sign/containment disagree'
    write(ROOT/'reports/original_full_route_scan.json',report)

if __name__=='__main__':initial_scan()
