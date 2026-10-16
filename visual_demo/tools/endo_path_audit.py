"""Read-only clearance checks against the artist's exact morphs (RAS mm)."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from endo_common import *
import vtk
from vtk.util.numpy_support import numpy_to_vtk

def surface(vertices, faces):
    points = vtk.vtkPoints(); points.SetData(numpy_to_vtk(vertices, deep=True))
    cells = vtk.vtkCellArray()
    for f in faces:
        cells.InsertNextCell(3, [int(i) for i in f])
    mesh = vtk.vtkPolyData(); mesh.SetPoints(points); mesh.SetPolys(cells)
    return mesh

def measure(vertices, faces, points):
    mesh = surface(vertices, faces)
    distance = vtk.vtkImplicitPolyDataDistance(); distance.SetInput(mesh)
    probe = vtk.vtkPolyData(); pp = vtk.vtkPoints(); pp.SetData(numpy_to_vtk(np.asarray(points), deep=True)); probe.SetPoints(pp)
    enclosed = vtk.vtkSelectEnclosedPoints(); enclosed.SetInputData(probe); enclosed.SetSurfaceData(mesh); enclosed.SetTolerance(1e-7); enclosed.Update()
    return np.array([abs(distance.EvaluateFunction(p)) for p in points]), np.array([bool(enclosed.IsInside(i)) for i in range(len(points))])

def run():
    protect()
    shapes = np.load(ROOT/'data/manual_v3_shapes_RAS_mm.npz')
    path = read(PATH); pts = np.array(path['points']); lengths = np.r_[0, np.cumsum(np.linalg.norm(np.diff(pts, axis=0), axis=1))]
    offsets = np.linspace(0, lengths[-1], 350)
    points = np.array([np.interp(offsets, lengths, pts[:,i]) for i in range(3)]).T
    report = {'path_sha256': sha(PATH), 'total_length_mm':float(lengths[-1]), 'states':{}}
    for s in [-.6, 0., 1.]:
        vertices=shapes['Basis']+max(-s,0)*(shapes['Contracted']-shapes['Basis'])+max(s,0)*(shapes['Expanded']-shapes['Basis'])
        d, inside=measure(vertices, shapes['faces'], points)
        report['states'][str(s)]={'clearance_mm': d.tolist(), 'inside':inside.tolist()}
    report['offsets_mm']=offsets.tolist()
    write(ROOT/'reports/path_scan.json',report)
    for lo in range(20,76,5):
        mask=(offsets>=lo)&(offsets<=lo+10)
        print(lo,lo+10,{s:{'min_mm':round(min(np.array(v['clearance_mm'])[mask]),3),'inside':bool(np.array(v['inside'])[mask].all())} for s,v in report['states'].items()})

if __name__=='__main__':run()
