"""Local engineering report + offline interactive route preview (no publication)."""
from full_route_common import *
from full_route_optimize import frames_at
from PIL import Image,ImageDraw,ImageFont
import os
os.environ.setdefault('MPLCONFIGDIR',str(ROOT/'data/matplotlib_cache'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from plotly.offline import get_plotlyjs

def overview(g,original,optimized,junctions):
    renderer=vtk.vtkRenderer();renderer.SetBackground(.97,.98,.98)
    mapper=vtk.vtkPolyDataMapper();mapper.SetInputData(g.mesh(-.4))
    actor=vtk.vtkActor();actor.SetMapper(mapper);actor.GetProperty().SetColor(.77,.44,.52);actor.GetProperty().SetOpacity(.13);renderer.AddActor(actor)
    def line(points,color):
        pp=vtk.vtkPoints();pp.SetData(numpy_to_vtk(points,deep=True))
        lines=vtk.vtkCellArray();lines.InsertNextCell(len(points))
        for i in range(len(points)):lines.InsertCellPoint(i)
        poly=vtk.vtkPolyData();poly.SetPoints(pp);poly.SetLines(lines)
        tube=vtk.vtkTubeFilter();tube.SetInputData(poly);tube.SetRadius(.16);tube.SetNumberOfSides(10);tube.Update()
        m=vtk.vtkPolyDataMapper();m.SetInputConnection(tube.GetOutputPort());a=vtk.vtkActor();a.SetMapper(m);a.GetProperty().SetColor(*color);a.GetProperty().LightingOff();renderer.AddActor(a)
    line(original,(.78,.2,.22));line(optimized,(0,.48,.44))
    markers=[('起点：保持',optimized[0]),('分叉 1',junctions[0]),('分叉 2',junctions[1]),('终点：横移 1.63 mm',optimized[-1])]
    for label,point in markers:
        sphere=vtk.vtkSphereSource();sphere.SetCenter(*point);sphere.SetRadius(.65);sphere.SetThetaResolution(20);sphere.SetPhiResolution(20)
        m=vtk.vtkPolyDataMapper();m.SetInputConnection(sphere.GetOutputPort());a=vtk.vtkActor();a.SetMapper(m);a.GetProperty().SetColor(.93,.65,.15);renderer.AddActor(a)
    camera=renderer.GetActiveCamera();camera.SetFocalPoint(14,14,-91);camera.SetPosition(170,-230,-55);camera.SetViewUp(0,0,1);camera.ParallelProjectionOn();camera.SetParallelScale(60)
    window=vtk.vtkRenderWindow();window.SetOffScreenRendering(1);window.SetSize(1400,1100);window.AddRenderer(renderer);window.SetMultiSamples(4);window.Render()
    capture=vtk.vtkWindowToImageFilter();capture.SetInput(window);capture.ReadFrontBufferOff();capture.Update()
    writer=vtk.vtkPNGWriter();writer.SetFileName(str(ROOT/'preview/route_overview.png'));writer.SetInputConnection(capture.GetOutputPort());writer.Write()
    image=Image.open(ROOT/'preview/route_overview.png').convert('RGB');draw=ImageDraw.Draw(image);font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',24)
    draw.text((35,25),'完整路线候选 · Contracted=0.4',font=font,fill='#173e36')
    draw.text((35,65),'红色：原路径     青色：优化路径     金色：起止点与分叉',font=font,fill='#46645d')
    for label,point in markers:
        renderer.SetWorldPoint(*point,1);renderer.WorldToDisplay();x,y,z=renderer.GetDisplayPoint();y=1100-y
        draw.text((x+15,y+8 if '2' not in label else y-30),label,font=font,fill='#173e36',stroke_width=2,stroke_fill='white')
    image.save(ROOT/'preview/route_overview.png');window.Finalize()

def build():
    g=Geometry();f=read(ROOT/'reports/feasibility.json');old=read(ROOT/'reports/original_full_route_scan.json');view=read(ROOT/'reports/view_validation.json');route=read(DEMO_PATH)
    original=np.array(read(SOURCE)['points']);p=np.array(route['points']);grid=np.load(ROOT/'data/validation_grid.npz')
    old_d=np.array(old['signed_clearance_mm']);old_arc=np.array(old['offsets_mm']);old_min=old_d.min(axis=0)
    plt.rcParams.update({'font.family':'Microsoft YaHei','axes.unicode_minus':False,'font.size':11})
    fig,axes=plt.subplots(2,1,figsize=(12,8),constrained_layout=True)
    axes[0].plot(old_arc,old_min,color='#c54949',label='原路径：15 状态扫描最小余量')
    axes[0].plot(route['original_arc_offsets_mm'],grid['clearance'].min(axis=0),color='#087f79',label='优化路径：57 状态采样最小余量')
    axes[0].plot(np.array(route['original_arc_offsets_mm'])[:-1],grid['continuous_lower_bound'].min(axis=0),color='#2164aa',label='优化路径：连续路径 × 连续形变保守下界',lw=1)
    axes[0].axhline(0,color='#333',lw=1);axes[0].axhline(1,color='#999',ls=':',label='本次视觉通行设计下界 1 mm')
    axes[0].set_ylabel('镜头光心至腔壁距离 / mm');axes[0].set_xlabel('对应原路线弧长 / mm');axes[0].legend(loc='lower left',fontsize=9);axes[0].grid(alpha=.2)
    axes[0].set_title('完整路线没有跳段：收缩态穿墙风险经局部路径调整消除',loc='left',fontweight='bold')
    times=np.array(route['times_seconds']);speeds=np.array(route['speed_mm_s'])
    axes[1].plot(times,speeds,color='#087f79',label='沿新路线速度')
    ax2=axes[1].twinx();u=times/f['duration_seconds'];ax2.plot(times,.3-.7*np.cos(2*np.pi*u),color='#b5527c',label='全模型统一状态 s')
    axes[1].set_xlabel('预览时间 / s');axes[1].set_ylabel('镜头速度 / mm/s');ax2.set_ylabel('全局形变状态 s');axes[1].grid(alpha=.2)
    for j in route['junctions']:
        t=np.interp(j,route['arc_lengths_mm'],times);axes[1].axvline(t,ls='--',color='#888');axes[1].text(t+.3,.7,'分叉',color='#555')
    axes[1].set_ylim(0,2.7);ax2.set_ylim(-.5,1.1)
    axes[1].legend(loc='upper left');ax2.legend(loc='upper right')
    fig.savefig(ROOT/'preview/clearance_and_timing.png',dpi=150);plt.close(fig)

    worst=float(old_arc[old_min.argmin()]);centers,tan,a,b=frames_at(original,np.array([worst]))
    xy=np.linspace(-4,4,161);xx,yy=np.meshgrid(xy,xy);cross=centers[0]+xx[...,None]*a[0]+yy[...,None]*b[0]
    field=np.array([g.clearance(cross.reshape(-1,3),s).reshape(xx.shape) for s in [-.4,0,1]])
    position=np.array([np.interp(worst,route['original_arc_offsets_mm'],p[:,i]) for i in range(3)])
    shift=position-centers[0];target=[np.dot(shift,a[0]),np.dot(shift,b[0])]
    fig,ax=plt.subplots(figsize=(7.5,6),constrained_layout=True)
    ax.contourf(xx,yy,np.min(field,axis=0),levels=[0,100],colors=['#d5eee6'])
    for i,(color,name) in enumerate([('#c14e78','Contracted=0.4'),('#6a737b','Reference'),('#236aaa','Expanded=1.0')]):
        ax.contour(xx,yy,field[i],levels=[0],colors=[color],linewidths=2);ax.plot([],[],color=color,label=name)
    ax.scatter([0],[0],c='#c54949',marker='x',s=100,label='原路径光心（在收缩腔壁外）')
    ax.scatter([target[0]],[target[1]],c='#087f79',s=65,label='优化路径光心')
    ax.set_aspect('equal');ax.set_xlabel('局部横截面轴 1 / mm');ax.set_ylabel('局部横截面轴 2 / mm');ax.grid(alpha=.2)
    ax.set_title(f'原路线 {worst:.2f} mm 附近横截面\n绿色为三主态共同内腔；连续状态安全性另由距离界验证')
    ax.legend(loc='upper left',fontsize=9);fig.savefig(ROOT/'preview/critical_cross_section.png',dpi=160);plt.close(fig)

    rows=np.genfromtxt(ROOT/'preview/frames.csv',delimiter=',',names=True)
    images=sorted((ROOT/'preview').glob('frame_*.png'))
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',15)
    sheet=Image.new('RGB',(1600,((len(images)+3)//4)*255),(19,25,29));draw=ImageDraw.Draw(sheet)
    snapshots=[]
    for i,path in enumerate(images):
        n=int(path.stem.split('_')[1]);row=rows[np.argmin(abs(rows['frame']-n))]
        x=i%4*400;y=i//4*255;sheet.paste(Image.open(path).resize((400,225)),(x,y))
        caption=f"{row['time']:.2f}s · C {row['contracted']:.2f} / E {row['expanded']:.2f} · 路程 {row['arc_mm']:.1f}mm"
        draw.text((x+7,y+230),caption,fill='white',font=font)
        snapshots.append({'image':'preview/'+path.name,'time':float(row['time']),'arc':float(row['arc_mm']),'c':float(row['contracted']),'e':float(row['expanded'])})
    sheet.save(ROOT/'preview/contact_sheet.jpg',quality=92)
    overview(g,original,p,sample(p,np.array(route['junctions'])))
    payload={'basis':g.basis.round(6).tolist(),'dc':g.dc.round(6).tolist(),'de':g.de.round(6).tolist(),'faces':g.faces.tolist(),'original':original.tolist(),'optimized':p.tolist(),'junctions':sample(p,np.array(route['junctions'])).tolist(),'snapshots':snapshots}
    html=HTML.replace('__PLOTLY__',get_plotlyjs()).replace('__DATA__',json.dumps(payload,separators=(',',':')))
    (ROOT/'index.html').write_text(html,encoding='utf8')
    protect();print('Report figures and interactive preview created',flush=True)

HTML='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>完整路线可行性与预览 · Contracted 0.4</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f5f6f7;color:#18322f;font:16px/1.7 system-ui,"Microsoft YaHei",sans-serif}main{max-width:1240px;margin:auto;padding:38px 32px 70px}h1{font-size:34px;line-height:1.25;margin:6px 0 15px}h2{font-size:23px;margin:0 0 15px}p{margin:10px 0}.eyebrow{color:#55736d;font-size:13px;letter-spacing:2px}.lead{font-size:18px;max-width:1000px}.status{display:inline-block;background:#dcefe7;color:#17634a;padding:4px 12px;border-radius:7px;font-size:14px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:15px;margin:25px 0}.card,section{background:white;border:1px solid #dbe4df;border-radius:12px;padding:22px}.card b{font-size:29px;display:block;font-weight:650}.card span{font-size:13px;color:#57706a}section{margin:24px 0}.note{background:#fff5e3;border-left:4px solid #d9a13e;padding:12px 18px;color:#694d26;font-size:15px}.controls{display:flex;flex-wrap:wrap;gap:15px;align-items:center}input[type=range]{width:330px;max-width:100%;accent-color:#168b7b}button{font:inherit;background:#eef5f2;border:1px solid #c4d9d2;color:#246959;border-radius:6px;padding:5px 12px;cursor:pointer}button:hover{background:#dceee6}#plot{height:640px}figure{margin:0}img{max-width:100%;height:auto;border-radius:7px}.gallery{display:grid;grid-template-columns:1fr;gap:12px}#scopeImage{width:100%;background:#222;aspect-ratio:16/9;object-fit:contain}table{border-collapse:collapse;width:100%;font-size:14px}td,th{text-align:left;padding:12px 10px;border-bottom:1px solid #e0e7e3}th{color:#3e6258}code{background:#edf3f0;padding:2px 5px;overflow-wrap:anywhere}a{color:#087f79}.subtle{color:#637a74;font-size:14px}.columns{display:grid;grid-template-columns:1.1fr 1fr;gap:25px}.footer{font-size:13px;color:#678079}.pass{color:#177552;font-weight:600}@media(max-width:750px){main{padding:20px 14px}.cards{grid-template-columns:1fr 1fr}.columns{grid-template-columns:1fr}#plot{height:460px}h1{font-size:27px}}</style>
<script>__PLOTLY__</script></head><body><main>
<div class="eyebrow">V-DEMO · 完整路线候选 · 2026-10-16</div><h1>在全局同步形变中，完整走完内镜路线</h1>
<div class="status">路径可行 · 预览待确认 · 未录制最终 MP4</div>
<p class="lead">当前人工 v3 模型存在可用的连续光心通道。候选路线保留原起点、两个分叉顺序和整体走向，局部居中后走到终端区；无需先修改模型。</p>
<div class="cards"><div class="card"><b>1.24 mm</b><span>全路径 × 全形变区间的保守壁面余量</span></div><div class="card"><b>89.18 mm</b><span>完整路线长度 · 原路线 86.53 mm</span></div><div class="card"><b>1.63 mm</b><span>终点横向调整 · 起点原位保留</span></div><div class="card"><b>45.93 s</b><span>建议完整周期 · 0.4 → 1.0 → 0.4</span></div></div>
<div class="note">需确认的变化：终点在同一终端区横向移动 1.63 mm，路线最大偏移 2.39 mm。此处评估的是内镜画面的光心与近裁剪空间，不是实体内镜半径或临床通行认证。</div>
<section><h2>1 · 检查完整路线与形变</h2><p>拖动旋转，滚轮缩放；点击图例可隐藏腔壁或路线。青色为优化路径，红色为原路径，金色点为按原顺序保留的两处分叉位置。起点重合，终点保留在原终端区。</p><div class="controls"><label>全模型统一状态 <b id="stateLabel">s = -0.40</b><br><input id="stateSlider" type="range" min="-40" max="100" value="-40" step="1"></label><button id="cButton">Contracted 0.4</button><button id="rButton">Reference</button><button id="eButton">Expanded 1.0</button><button id="resetView">恢复视角</button></div><div id="plot"></div><p class="subtle">滑块对整个网格同时赋予同一组 Shape Keys 权重；没有近处或远处的时间偏移。部分固定端口不移动，这是人工模型原有的位移幅度，并非延迟。</p></section>
<section><h2>2 · Godot 第一人称预览帧</h2><p>以下画面来自实际运行的新独立场景，覆盖起点、两个分叉和终点。拖动可检查选定时刻；F6 场景提供连续实时播放。不是最终视频。</p><div class="gallery"><img id="scopeImage" alt="Godot 内镜预览"><div class="controls"><input id="frameSlider" type="range" min="0" value="0" step="1"><b id="frameLabel"></b></div></div><p class="subtle">已核验 1379 个姿态样本：路程单调前进，最大相邻帧旋转约 0.61°；首、中、末实际权重为 (0.4, 0) → (0, 1) → (0.4, 0)。</p></section>
<section><h2>3 · 不是只避开某一帧</h2><p>路径在 <b>s ∈ [-0.4, 1.0]</b> 的 57 个状态上取样（步长 0.025），每个状态检查全部 869 个路径点。再用壁面最大位移和相邻路径点距离，为未采样的中间位置与中间状态建立保守距离下界。因此不依赖“趁扩张时才通过”的时机，也不需要局部形变延迟。</p><img src="preview/clearance_and_timing.png" alt="全路线壁面距离和同步时间曲线"><p class="subtle">连续界 = 四个相邻样本中的最小距离 − 半段路径长度 − 半段状态间隔内最大顶点位移。所有区间下界均为正，最低 1.239 mm；计入 Godot 位置误差后基本不变。0.05 mm 近裁剪平面最远角点距光心约 0.114 mm，仍留有约 1.126 mm 的保守余量。</p></section>
<section><h2>4 · 原路径的问题与局部调整</h2><div class="columns"><div><p>原路径在 Contracted=0.4 时，约 <b>78.3–85.3 mm</b> 区段位于腔壁外，最严重处约 80.64 mm，穿出约 0.71 mm。原终点虽在腔内，但只剩约 0.20 mm 壁面余量。</p><p>优化仅改变独立演示路径，逐个经过原路线对应的纵向区段，没有跳段或传送。局部横向移动后找到了共同内腔中的连续路径，终点移动约 1.63 mm。</p><p class="pass">因此：按本次视觉空间标准，不需要 v4 局部修形。保留人工 v3；最终录制前请先确认候选路线。</p></div><img src="preview/critical_cross_section.png" alt="原路径问题位置的三态横截面与优化位置"></div></section>
<section><h2>5 · 验证结果与交付</h2><table><thead><tr><th>项目</th><th>结果</th></tr></thead><tbody><tr><td>Contracted=0.4 / Reference / Expanded=1</td><td>最小采样余量 1.392 / 1.522 / 1.519 mm</td></tr><tr><td>整个形变区间与完整路线</td><td>连续保守下界 1.239 mm，无壁面交叉</td></tr><tr><td>三主态中心视线抽样</td><td>最短前向空间约 5.38 mm；这项为抽样值，不是连续视野下界</td></tr><tr><td>分叉位置（新路线弧长）</td><td>72.218 mm → 79.562 mm，原顺序保留</td></tr><tr><td>运行验证</td><td>Godot 4.7 / Forward+ / RTX 4070 Ti，1379 帧姿态记录</td></tr><tr><td>模型与权威研究数据</td><td>校验保持不变，未改写 main.tscn、原控制器或原路径</td></tr></tbody></table><p>运行 <code>godot_sim/visual_demo_full_route_preview.tscn</code>，按 F6。新路径为 <code>godot_sim/visual_demo/data/full_route_c04.json</code>，包含位置、forwards、分叉弧长、速度和统一时间表。</p><p><a href="完整路线可行性报告.md">完整文字报告与运行方法</a> · <a href="reports/feasibility.json">几何可行性明细</a> · <a href="reports/view_validation.json">Godot 及视野验证</a> · <a href="reports/godot_preview.log">运行日志</a> · <a href="preview/contact_sheet.jpg">全部预览帧总览</a></p></section>
<p class="footer">报告为本地离线文件，不上传数据。人工模型及权威路径仅用于只读几何分析。旧版最终 MP4 未更新；新完整路线最终 MP4 等用户确认后制作。</p></main>
<script>const D=__DATA__;let state=-.4;const component=(v,k)=>v.map(p=>p[k]);const moved=s=>D.basis.map((p,i)=>p.map((v,k)=>v+Math.max(-s,0)*D.dc[i][k]+Math.max(s,0)*D.de[i][k]));
const v=moved(state);const trace=(p,name,color)=>({type:'scatter3d',mode:'lines',x:component(p,0),y:component(p,1),z:component(p,2),name,line:{color,width:6},hovertemplate:name+'<br>R %{x:.2f}<br>A %{y:.2f}<br>S %{z:.2f}<extra></extra>'});
const camera={eye:{x:1.6,y:-2.1,z:.7},up:{x:0,y:0,z:1},projection:{type:'orthographic'}};
const traces=[{type:'mesh3d',x:component(v,0),y:component(v,1),z:component(v,2),i:component(D.faces,0),j:component(D.faces,1),k:component(D.faces,2),color:'#d995a5',opacity:.16,name:'人工 v3 腔壁',showlegend:true,hoverinfo:'skip',lighting:{ambient:.75,diffuse:.5,specular:.1}},trace(D.original,'原路径','#c74949'),trace(D.optimized,'优化路径','#007f79'),{type:'scatter3d',mode:'markers+text',x:component(D.junctions,0),y:component(D.junctions,1),z:component(D.junctions,2),marker:{size:5,color:'#e7aa32'},text:['分叉 1','分叉 2'],textposition:'top center',name:'分叉顺序'},{type:'scatter3d',mode:'markers+text',x:[D.optimized[0][0],D.optimized.at(-1)[0]],y:[D.optimized[0][1],D.optimized.at(-1)[1]],z:[D.optimized[0][2],D.optimized.at(-1)[2]],marker:{size:5,color:'#1b443c'},text:['起点（保持）','终点（横移 1.63 mm）'],textposition:'top center',name:'起止位置'}];
Plotly.newPlot('plot',traces,{margin:{l:0,r:0,t:15,b:0},paper_bgcolor:'#fff',font:{family:'Microsoft YaHei, sans-serif'},legend:{orientation:'h',x:0,y:1.03},scene:{aspectmode:'data',camera,xaxis:{title:'R / mm'},yaxis:{title:'A / mm'},zaxis:{title:'S / mm'}},uirevision:'route'},{responsive:true,displaylogo:false});
function setState(s){state=s;document.getElementById('stateSlider').value=Math.round(s*100);document.getElementById('stateLabel').textContent=`s = ${s.toFixed(2)} · C ${Math.max(-s,0).toFixed(2)} / E ${Math.max(s,0).toFixed(2)}`;const v=moved(s);Plotly.restyle('plot',{x:[component(v,0)],y:[component(v,1)],z:[component(v,2)]},[0]);}
document.getElementById('stateSlider').addEventListener('input',e=>setState(Number(e.target.value)/100));document.getElementById('cButton').onclick=()=>setState(-.4);document.getElementById('rButton').onclick=()=>setState(0);document.getElementById('eButton').onclick=()=>setState(1);document.getElementById('resetView').onclick=()=>Plotly.relayout('plot',{'scene.camera':camera});
const frameSlider=document.getElementById('frameSlider');frameSlider.max=D.snapshots.length-1;function showFrame(i){const f=D.snapshots[i];document.getElementById('scopeImage').src=f.image;document.getElementById('frameLabel').textContent=`${f.time.toFixed(2)} s · 新路线 ${f.arc.toFixed(2)} mm · C ${f.c.toFixed(2)} / E ${f.e.toFixed(2)}`;}frameSlider.oninput=e=>showFrame(Number(e.target.value));showFrame(0);
window.previewReady=true;</script></body></html>'''

if __name__=='__main__':build()
