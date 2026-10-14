"""Static inspectable figures of existing geometry; no image or mesh editing."""
from audit_reference_capacity import *
import os
cache=PROJECT/'analysis/irrigation_baseline/capacity_v2_plot_cache'
cache.mkdir(parents=True,exist_ok=True)
os.environ['MPLCONFIGDIR']=str(cache)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def plot():
    font=font_manager.FontProperties(fname='C:/Windows/Fonts/msyh.ttc')
    font_manager.fontManager.addfont('C:/Windows/Fonts/msyh.ttc')
    plt.rcParams['font.family']=font.get_name();plt.rcParams['axes.unicode_minus']=False
    r=read_json(OUT/'reference_capacity_audit.json');_,a=verify_sources();v=a['cavity_reference_vertices']-ORIGIN;f=a['cavity_faces']
    fixed=np.load(PROJECT/'deformation/p1_masks/port_fixed_masks.npy')
    colors=['#396cbe','#e59a28','#bd465c'];names=['BLADDER','IN_01','IN_02']
    fig=plt.figure(figsize=(12,7),layout='constrained')
    for index,azim in enumerate([-65,115]):
        ax=fig.add_subplot(1,2,index+1,projection='3d')
        facecolors=np.tile(matplotlib.colors.to_rgba('#c7cdd4'),(len(f),1))
        for mask,color in zip(fixed,colors):facecolors[mask[f].all(1)]=matplotlib.colors.to_rgba(color)
        ax.add_collection3d(Poly3DCollection(v[f],facecolors=facecolors,edgecolors='none',rasterized=True))
        for p,color in zip(r['artificial_distal_proxies'],colors):
            ring=p['boundary_vertex_ids'];ring=ring+[ring[0]]
            q=v[ring];ax.plot(q[:,0],q[:,1],q[:,2],color='#161d26',linewidth=1.8)
            c=np.mean(q,axis=0);ax.text(c[0],c[1],c[2],p['id'],fontsize=9)
        ax.set_xlim(v[:,0].min()-5,v[:,0].max()+5);ax.set_ylim(v[:,1].min()-5,v[:,1].max()+5);ax.set_zlim(v[:,2].min()-5,v[:,2].max()+5)
        ax.set_box_aspect(np.ptp(v,axis=0));ax.view_init(elev=16,azim=azim)
        ax.set_xlabel('X（mm）');ax.set_ylabel('Y（mm）');ax.set_zlabel('Z（mm）')
        ax.set_title('同一原始腔体 · 视角 '+str(index+1))
    fig.suptitle('人工远端固定区域与核算边界：黑线不是已批准的解剖切面\n只读原参考网格；显示坐标减去 [16,16,-81] mm',fontsize=13)
    fig.savefig(OUT/'artificial_interface_accounting.png',dpi=160);plt.close(fig)
    fig,ax=plt.subplots(figsize=(10,5))
    fig.subplots_adjust(left=.11,right=.97,bottom=.2,top=.86)
    rows=r['legacy_debug_volume_levels'];x=[p['legacy_u'] for p in rows];y=[p['closed_mesh_volume_mL'] for p in rows]
    ax.plot(x,y,'o-',color='#286ca5',linewidth=2)
    for xx,yy in zip(x,y):ax.annotate(f'{yy:.3f} mL',(xx,yy),xytext=(4,10),textcoords='offset points')
    ax.set(xlabel='旧工程参数 u（只核对已验收 0～1 范围）',ylabel='完整封闭计算网格体积（mL）',title='旧 0.2 mm 工程场的实际体积曲线：不是新的正常容量上下界')
    ax.set_xlim(-.05,1.12);ax.set_ylim(min(y)-.2,max(y)+.25);ax.grid(alpha=.25)
    fig.text(.5,.015,'完整网格含人工通道。没有计算 Contracted；未将旧 Expanded 认定为生理 Vmax。',ha='center',fontsize=10)
    fig.savefig(OUT/'legacy_debug_volume_curve.png',dpi=160);plt.close(fig)
    print('Saved two read-only scientific figures.')


if __name__=='__main__':plot()
