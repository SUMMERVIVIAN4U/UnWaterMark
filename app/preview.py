"""Bounded, visibly marked preview; never return the clean result on failure."""
import io,subprocess,tempfile,threading
from pathlib import Path
from PIL import Image,ImageDraw
from fastapi import HTTPException
_LOCK=threading.Lock()
SCALE="scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease:force_divisible_by=2"

def make_preview(folder):
    folder=Path(folder);output=folder/'preview-v3.mp4'
    if output.is_file():return output
    if not _LOCK.acquire(blocking=False):raise HTTPException(429,'正在准备预览，请稍后重试')
    try:
        if output.is_file():return output
        with tempfile.TemporaryDirectory(dir=folder,prefix='preview-') as temp:
            temp=Path(temp)
            raw=subprocess.check_output(['ffmpeg','-v','error','-threads','1','-i',str(folder/'result.mp4'),'-vf',SCALE,'-frames:v','1','-f','image2pipe','-vcodec','png','-'],stderr=subprocess.PIPE,timeout=20)
            with Image.open(io.BytesIO(raw)) as frame:w,h=frame.size
            overlay=Image.new('RGBA',(w,h),(0,0,0,0));label=Image.new('RGBA',(92,20),(20,20,20,120))
            ImageDraw.Draw(label).text((5,4),'PREVIEW',fill=(255,255,255,220))
            overlay.alpha_composite(label,(max(0,w-100),8))
            overlay.save(temp/'mark.png')
            subprocess.run(['ffmpeg','-v','error','-y','-threads','1','-i',str(folder/'result.mp4'),'-i',str(temp/'mark.png'),'-filter_complex_threads','1','-filter_complex',f'[0:v]{SCALE}[v];[v][1:v]overlay=0:0,format=yuv420p[out]','-map','[out]','-an','-t','10','-c:v','libx264','-threads','1','-preset','ultrafast','-crf','20','-movflags','+faststart',str(temp/'preview.mp4')],check=True,stderr=subprocess.PIPE,timeout=30)
            (temp/'preview.mp4').replace(output)
        return output
    except (subprocess.SubprocessError,OSError) as exc:
        raise HTTPException(503,'预览暂时无法生成，请稍后重试') from exc
    finally:_LOCK.release()

_POSTER_LOCK=threading.Lock()
def make_poster(folder,working_file):
    """A plain image can load even when a mobile player defers all media loading."""
    folder=Path(folder);output=folder/'source-poster-v1.jpg'
    if output.is_file():return output
    if not _POSTER_LOCK.acquire(timeout=3):raise HTTPException(429,'正在准备视频画面，请稍后重试')
    try:
        if output.is_file():return output
        with tempfile.TemporaryDirectory(dir=folder,prefix='poster-') as temp:
            target=Path(temp)/'frame.jpg'
            subprocess.run(['ffmpeg','-v','error','-threads','1','-i',str(folder/working_file),'-map','0:v:0','-vf',"scale=w='min(960,iw)':h='min(960,ih)':force_original_aspect_ratio=decrease",'-frames:v','1','-threads','1','-q:v','2',str(target)],check=True,stderr=subprocess.PIPE,timeout=20)
            target.replace(output)
        return output
    except (subprocess.SubprocessError,OSError) as exc:
        raise HTTPException(503,'视频画面暂时无法生成，请点击加载重试') from exc
    finally:_POSTER_LOCK.release()
