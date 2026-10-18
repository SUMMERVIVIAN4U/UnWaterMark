"""Upload-only conversion into the strict internal CFR working-video contract."""
import hashlib
import json
import math
import re
import subprocess
from fractions import Fraction
from pathlib import Path
from .media import inspect_video, MAX_BYTES
from .hosting import HostingPolicy

POLICY = dict(version=1, vfr_target_fps=30, fps_range=[1,120], video='H.264 8-bit yuv420p MP4, CFR, square pixels, zero video start', audio='Zero-based AAC; preserve relative offset by trimming pre-video samples or padding silence', rotation_degrees=[0,90,180,270], hdr=False, max_audio_streams=1, max_bytes=MAX_BYTES, extensions=['mp4','mov','m4v'], geometry='No arbitrary downscale; correct SAR and pad each odd edge by at most one pixel', timeouts_seconds=dict(probe=180,transcode=180))

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def probe(args,path):
    return json.loads(subprocess.check_output(['ffprobe','-v','error',*args,'-of','json',str(path)],stderr=subprocess.PIPE,timeout=180))

def rotation(stream):
    matrices=[d for d in stream.get('side_data_list',[]) if d.get('side_data_type')=='Display Matrix']
    angle=float(stream.get('tags',{}).get('rotate',0))
    if len(matrices)>1:raise ValueError('不支持此显示矩阵，请先导出普通 SDR 视频')
    if matrices:
        d=matrices[0];angle=float(d.get('rotation',angle))
        rows=[list(map(int,line.split(':',1)[1].split())) for line in d.get('displaymatrix','').strip().splitlines() if ':' in line]
        if len(rows)!=3 or any(len(row)!=3 for row in rows):raise ValueError('无法验证视频显示矩阵')
        a,b,u,c,e,v,x,y,w=[n for row in rows for n in row]
        # Pure orthogonal rotation only: no mirror, translation, scale or perspective.
        if any((u,v,x,y)) or w!=1073741824 or abs(a*a+b*b-65536**2)>131072 or abs(c*c+e*e-65536**2)>131072 or abs(a*c+b*e)>131072 or a*e-b*c<=0:
            raise ValueError('不支持带镜像、缩放或透视的显示矩阵')
    if not math.isfinite(angle) or abs(angle/90-round(angle/90))>.001:raise ValueError('仅支持 90、180、270 度正交旋转')
    return round(angle)%360

def prepare_upload(path, inspector=inspect_video):
    path=Path(path)
    try:
        streams=probe(['-show_streams'],path)['streams'];videos=[s for s in streams if s['codec_type']=='video' and not s.get('disposition',{}).get('attached_pic')];audio=[s for s in streams if s['codec_type']=='audio']
        if len(videos)!=1:raise ValueError('仅支持包含一条视频流的文件')
        if len(audio)>1:raise ValueError('暂只支持单音轨视频，请先选择一个音轨导出')
        s=videos[0]
        hosted=HostingPolicy.from_env();hosted.check_stream(s)
        if s.get('color_transfer') in {'smpte2084','arib-std-b67'} or any(d.get('side_data_type') in {'Mastering display metadata','Content light level metadata','DOVI configuration record'} for d in s.get('side_data_list',[])):
            raise ValueError('暂不支持 HDR 视频，请先导出 SDR 8 位版本')
        pix=s.get('pix_fmt','')
        if pix not in {'yuv420p','yuvj420p','yuv422p','yuvj422p','yuv444p','yuvj444p','nv12','rgb24','bgr24','gbrp','gray'}:raise ValueError('暂只支持 SDR 8 位像素格式')
        frames=probe(['-select_streams','v:0','-show_frames','-show_entries','frame=best_effort_timestamp_time,duration_time,pkt_duration_time'],path).get('frames',[])
        if not frames or any('best_effort_timestamp_time' not in f for f in frames):raise ValueError('视频缺少有效时间戳')
        times=[float(f['best_effort_timestamp_time']) for f in frames]
        if any(not math.isfinite(t) for t in times) or any(b<=a for a,b in zip(times,times[1:])):raise ValueError('视频时间戳缺失或顺序异常')
        rate=None
        candidates=[s.get('r_frame_rate','0/1'),s.get('avg_frame_rate','0/1')]
        if len(times)>1:candidates.append(str(Fraction((len(times)-1)/(times[-1]-times[0])).limit_denominator(100000)))
        for candidate in candidates:
            f=Fraction(candidate)
            if f>0 and all(abs((t-times[0])-i/float(f))<=.001 for i,t in enumerate(times)):rate=f;break
        declared=Fraction(s.get('avg_frame_rate','0/1'))
        if not 1<=float(rate or declared)<=120:raise ValueError('支持的帧率范围为 1–120 fps；此视频帧率异常')
        # A regular timestamp grid can still end in a long final display hold.
        # Nonterminal packet durations may overlap later presentation frames (MOV);
        # they do not extend the actual displayed timeline. Only the final frame
        # determines the presentation endpoint.
        last_duration=float(frames[-1].get('duration_time',frames[-1].get('pkt_duration_time',1/float(rate or declared))))
        if not math.isfinite(last_duration) or last_duration<=0:raise ValueError('视频末帧显示时长无效')
        tail_mismatch=rate is not None and abs(last_duration-1/float(rate))>max(.002,.1/float(rate))
        vfr=rate is None or tail_mismatch;target=Fraction(30) if vfr else rate
        if any(b-a>10 for a,b in zip(times,times[1:])):raise ValueError('视频时间戳间隔异常')
        rot=rotation(s);sar=Fraction(s.get('sample_aspect_ratio','1:1').replace(':','/')) if s.get('sample_aspect_ratio') not in {None,'N/A','0:1'} else Fraction(1)
        if sar<=0 or sar>16 or sar<Fraction(1,16):raise ValueError('视频像素比例异常')
        start=times[0];a_start=float(audio[0].get('start_time',0)) if audio else 0
        if not math.isfinite(a_start):raise ValueError('音频缺少有效时间戳')
        w,h=int(s['width']),int(s['height']);reasons=[];warnings=[]
        if vfr:reasons.append('VFR 转为 30 fps 恒定帧率');warnings.append('VFR 转换可能重复或丢弃帧；目标为 30 fps')
        if tail_mismatch:reasons.append('保留末帧实际显示时长，按 30 fps 重复显示保持画面')
        if rot:reasons.append(f'应用 {rot}° 显示旋转')
        if sar!=1:reasons.append(f'校正非方形像素 {sar}')
        if w%2 or h%2:reasons.append('奇数边缘补齐最多 1 像素')
        if abs(start)>.001:reasons.append('视频时间轴归零')
        if audio and abs(a_start-start)>.001:reasons.append('保留音画相对偏移：裁剪视频开始前音频或补静音')
        if s.get('codec_name')!='h264' or pix!='yuv420p':reasons.append('转为浏览器兼容 H.264 / yuv420p')
        if audio and audio[0].get('codec_name')!='aac':reasons.append('音频转为 AAC')
        hosted.check_stream(dict(width=max(2,round(w*float(sar))),height=h,duration=times[-1]-start+last_duration,avg_frame_rate=str(target)))
        original_sha=sha(path)
        source=dict(width=w,height=h,codec=s.get('codec_name'),pixel_format=pix,fps=float(rate or declared),vfr=vfr,video_start=start,audio_start=a_start if audio else None,audio_count=len(audio),sample_aspect_ratio=str(sar),rotation=rot,presentation_duration=times[-1]-start+last_duration,last_frame_duration=last_duration)
        commands=[];working=path
        if reasons:
            warnings.append('工作视频会重新编码为 H.264，画质可能变化' + ('；音轨重新编码为 AAC，存在编码填充与音质变化' if audio else '；无音轨输入保持静音'))
            corrected_w=max(1,round(w*float(sar)))
            filters=[]
            if sar!=1:filters.append(f'scale={corrected_w}:{h}')
            filters.append('setsar=1')
            if rot==90:filters.append('transpose=cclock')
            elif rot==270:filters.append('transpose=clock')
            elif rot==180:filters+=['hflip','vflip']
            filters+=['pad=ceil(iw/2)*2:ceil(ih/2)*2','setpts=PTS-STARTPTS']
            if vfr:filters.append('fps=30:round=near')
            duration=len(times)/float(target) if not vfr else times[-1]-start+last_duration
            working=path.parent/'working.mp4'
            args=['ffmpeg','-y','-v','error','-xerror','-threads','2','-filter_threads','2','-copyts','-noautorotate','-display_rotation:v:0','0','-i',str(path),'-map','0:v:0','-map','0:a:0?','-vf',','.join(filters),'-c:v','libx264','-threads','2','-preset','fast','-crf','18','-pix_fmt','yuv420p','-r',str(target),'-fps_mode','cfr','-map_metadata','-1','-metadata:s:v:0','rotate=0']
            if audio:args+=['-af',f'atrim=start={start},asetpts=PTS-({start})/TB,aresample=async=1:first_pts=0,apad','-c:a','aac']
            args+=['-t',str(duration),'-movflags','+faststart',str(working)];commands.append(args)
            subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE,timeout=180)
            meta=inspector(working)
            if abs(meta['duration']-duration)>1/float(target)+.002:raise ValueError('规范化后视频时长校验失败')
        else:meta=inspector(path)
        hosted.check_working(meta)
        meta.update(working_file=working.name,normalization=dict(applied=bool(reasons),reasons=reasons,warnings=warnings,source=source,working=dict(width=meta['width'],height=meta['height'],fps=meta['fps'],duration=meta['duration']),original_sha256=original_sha,working_sha256=sha(working)))
        # Stored locally for lineage/debugging; never expose private filesystem paths in API metadata.
        (path.parent/'preparation.json').write_text(json.dumps(dict(normalization=meta['normalization'],commands=commands),ensure_ascii=False,indent=2))
        return meta
    except (subprocess.SubprocessError,KeyError,IndexError,ZeroDivisionError,OverflowError,json.JSONDecodeError) as exc:
        raise ValueError('视频损坏、处理超时或无法完整解码') from exc
