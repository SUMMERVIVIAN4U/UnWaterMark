import json, subprocess, io
from fractions import Fraction
from pathlib import Path
from PIL import Image
MAX_BYTES=100*1024*1024

def validate_name(name,size):
    if Path(name).suffix.lower() not in {'.mp4','.mov','.m4v'}:raise ValueError('仅支持 MP4、MOV、M4V 视频')
    if size>MAX_BYTES:raise ValueError('视频不能超过 100 MiB')

def inspect_video(path):
    try:
        raw=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-show_streams','-show_frames','-show_entries','frame=best_effort_timestamp_time:stream=width,height,avg_frame_rate,r_frame_rate,duration,nb_frames,sample_aspect_ratio,start_time:stream_tags=rotate:stream_side_data','-of','json',str(path)],stderr=subprocess.PIPE,timeout=180))
        s=raw['streams'][0];times=[float(f['best_effort_timestamp_time']) for f in raw['frames'] if 'best_effort_timestamp_time' in f]
        fps=float(Fraction(s['avg_frame_rate']));w,h=s['width'],s['height']
        if not times or fps<=0:raise ValueError('没有可解码的视频帧')
        if abs(times[0])>0.001:raise ValueError('暂不支持非零视频起始时间')
        if any(d.get('side_data_type')=='Display Matrix' for d in s.get('side_data_list',[])) or float(s.get('tags',{}).get('rotate',0))%360:raise ValueError('暂不支持旋转或显示矩阵视频，请先导出无旋转版本')
        sar=s.get('sample_aspect_ratio','1:1')
        if sar not in ('N/A','0:1') and Fraction(sar.replace(':','/'))!=1:raise ValueError('暂不支持非方形像素视频')
        if w%2 or h%2:raise ValueError('暂不支持奇数尺寸视频')
        # Container average rates can disagree with the actual presentation timeline.
        # Accept a rate only when every decoded timestamp fits its constant grid.
        rates=[s.get('r_frame_rate','0/1'),s['avg_frame_rate']]
        if len(times)>1 and times[-1]>times[0]:
            rates.append(str(Fraction((len(times)-1)/(times[-1]-times[0])).limit_denominator(100000)))
        for candidate in rates:
            rate=Fraction(candidate)
            if rate>0 and all(abs((t-times[0])-i/float(rate))<=.001 for i,t in enumerate(times)):
                fps=float(rate);fps_fraction=str(rate);break
        else:raise ValueError('暂不支持可变帧率 VFR 视频')
        subprocess.run(['ffmpeg','-v','error','-xerror','-i',str(path),'-map','0:v:0','-f','null','-'],check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=180)
        audio=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','a','-show_entries','stream=codec_name,start_time','-of','json',str(path)],timeout=180))['streams']
        if len(audio)>1:raise ValueError('暂只支持单音轨视频，请先选择一个音轨导出')
        if any(abs(float(a.get('start_time',0)))>0.05 for a in audio):raise ValueError('暂不支持音频起始偏移超过50毫秒的视频')
        return dict(video_start=times[0],sample_aspect_ratio=sar,display_transforms=s.get('side_data_list',[]),audio_streams=audio,audio_count=len(audio),width=w,height=h,fps=fps,fps_fraction=fps_fraction,duration=len(times)/fps,frames=len(times),has_audio=bool(audio),audio_codec=audio[0]['codec_name'] if audio else None)
    except (subprocess.SubprocessError,KeyError,IndexError,ZeroDivisionError,json.JSONDecodeError) as e:raise ValueError('视频损坏或无法完整解码') from e

def validate_mask(data,width,height):
    try:
        im=Image.open(io.BytesIO(data))
        if im.format!='PNG' or im.size!=(width,height):raise ValueError('蒙版必须是与视频尺寸一致的 PNG')
        im=im.convert('L')
        if not im.getbbox():raise ValueError('请先绘制需要去除的区域')
        return im
    except (OSError,Image.DecompressionBombError) as e:raise ValueError('无效 PNG 蒙版') from e
