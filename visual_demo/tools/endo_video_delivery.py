"""FFmpeg conversion and decoded-frame checks; no changes to authoritative inputs."""
import sys, subprocess, json, re
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from endo_common import *
sys.path.insert(0, str(ROOT/'vendor'))
import imageio_ffmpeg
from PIL import Image, ImageDraw

FFMPEG=imageio_ffmpeg.get_ffmpeg_exe()
RECORDINGS=PROJECT/'recordings'

def frames(path, small=True):
    reader=imageio_ffmpeg.read_frames(str(path),pix_fmt='rgb24',output_params=['-vf','scale=480:270'] if small else [])
    meta=next(reader)
    width,height=(480,270) if small else meta['size']
    data=np.stack([np.frombuffer(f,dtype=np.uint8).reshape(height,width,3) for f in reader])
    return meta,data

def run(name):
    protect()
    prefix=RECORDINGS/name
    telemetry=np.genfromtxt(str(prefix)+'_frames.csv',delimiter=',',names=True)
    meta,avi=frames(prefix.with_suffix('.avi'))
    comparisons=[]
    for i in [0,len(telemetry)//4,len(telemetry)//2,3*len(telemetry)//4,len(telemetry)-1]:
        snapshot=np.asarray(Image.open(str(prefix)+f'_{i:04d}.png').convert('RGB').resize((480,270)),dtype=float)
        errors=np.abs(avi.astype(float)-snapshot).mean((1,2,3))
        comparisons.append({'telemetry_frame':i,'avi_nearest_frame':int(errors.argmin()),'mae':float(errors.min())})
    print('AVI metadata',meta,'decoded frames',len(avi),'snapshot correspondence',comparisons,flush=True)
    # Godot 4.7 flushes one extra final frame when quit() is issued post-draw.
    # Retain frames 0..N inclusive, with both exact endpoint states.
    count=len(telemetry)
    if len(avi) not in (count,count+1):raise ValueError('Unexpected Movie Maker frame count')
    cmd=[FFMPEG,'-y','-hide_banner','-i',str(prefix.with_suffix('.avi')),'-an','-frames:v',str(count),
         '-vf','scale=in_color_matrix=bt601:out_color_matrix=bt709:in_range=pc:out_range=tv',
         '-c:v','libx264','-preset','slow','-crf','17','-pix_fmt','yuv420p',
         '-color_range','tv','-colorspace','bt709','-color_trc','bt709','-color_primaries','bt709',
         '-video_track_timescale','15360','-movflags','+faststart',str(prefix.with_suffix('.mp4'))]
    result=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)
    (ROOT/'reports'/f'{name}_ffmpeg.log').write_bytes(result.stdout)
    result.check_returncode()
    m,video=frames(prefix.with_suffix('.mp4'))
    # Decode every frame; changes measure gross cut/flash anomalies, not a clinical certification.
    differences=np.abs(np.diff(video.astype(float),axis=0)).mean((1,2,3))
    report={'avi_metadata':meta,'avi_decoded_frames':len(avi),'mp4_metadata':m,'mp4_decoded_frames':len(video),
            'snapshot_correspondence':comparisons,'endpoint_inclusive_samples':count,
            'first_weights':[float(telemetry['contracted'][0]),float(telemetry['expanded'][0])],
            'middle_weights':[float(telemetry['contracted'][count//2]),float(telemetry['expanded'][count//2])],
            'last_weights':[float(telemetry['contracted'][-1]),float(telemetry['expanded'][-1])],
            'frame_luminance_range':[float(video.mean((1,2,3)).min()),float(video.mean((1,2,3)).max())],
            'adjacent_frame_MAE_max_8bit':float(differences.max()),'adjacent_frame_MAE_median_8bit':float(np.median(differences)),
            'mp4_sha256':sha(prefix.with_suffix('.mp4')),'command':cmd}
    assert tuple(m['source_size'])==(1920,1080) and m['fps']==meta['fps'] and len(video)==count
    assert np.allclose(report['first_weights'],[.6,0]) and np.allclose(report['middle_weights'],[0,1]) and np.allclose(report['last_weights'],[.6,0])
    sheet=Image.new('RGB',(1440,3*290),(15,15,15));draw=ImageDraw.Draw(sheet)
    for slot,i in enumerate(np.linspace(0,count-1,9).round().astype(int)):
        x=slot%3*480;y=slot//3*290
        sheet.paste(Image.fromarray(video[i]),(x,y))
        draw.text((x+8,y+273),f"{i/30:.2f}s | C={telemetry['contracted'][i]:.3f} E={telemetry['expanded'][i]:.3f}",fill='white')
    sheet.save(str(prefix)+'_contact_sheet.jpg',quality=92)
    write(ROOT/'reports'/f'{name}_video_validation.json',report)
    print(json.dumps(report,ensure_ascii=True,indent=2),flush=True)
    protect()

if __name__=='__main__':run(sys.argv[1])
