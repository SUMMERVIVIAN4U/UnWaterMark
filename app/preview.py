"""Bounded, visibly marked preview; never return the clean result on failure."""
import io,subprocess,tempfile,threading
from pathlib import Path
from PIL import Image,ImageDraw
from fastapi import HTTPException
_LOCK=threading.Lock()
SCALE='scale=480:480:force_original_aspect_ratio=decrease:force_divisible_by=2'

def make_preview(folder):
    folder=Path(folder);output=folder/'preview-v1.mp4'
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
            for y in range(0,h,90):
                for x in range(0,w,130):overlay.alpha_composite(label,(x,y))
            overlay.save(temp/'mark.png')
            subprocess.run(['ffmpeg','-v','error','-y','-threads','1','-i',str(folder/'result.mp4'),'-i',str(temp/'mark.png'),'-filter_complex_threads','1','-filter_complex',f'[0:v]{SCALE}[v];[v][1:v]overlay=0:0,format=yuv420p[out]','-map','[out]','-an','-t','3','-c:v','libx264','-threads','1','-preset','ultrafast','-crf','28','-movflags','+faststart',str(temp/'preview.mp4')],check=True,stderr=subprocess.PIPE,timeout=30)
            (temp/'preview.mp4').replace(output)
        return output
    except (subprocess.SubprocessError,OSError) as exc:
        raise HTTPException(503,'预览暂时无法生成，请稍后重试') from exc
    finally:_LOCK.release()
