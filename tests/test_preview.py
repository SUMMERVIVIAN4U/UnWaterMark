import json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def test_preview_is_marked_short_and_cached(tmp_path):
    from app.preview import make_preview
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=blue:s=640x360:r=12','-t','12','-c:v','libx264','-pix_fmt','yuv420p',str(tmp_path/'result.mp4')],check=True)
    result=make_preview(tmp_path)
    data=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(result)]))
    assert 9.9<=float(data['format']['duration'])<=10.1 and (data['streams'][0]['width'],data['streams'][0]['height'])==(640,360)
    assert len(data['streams'])==1
    from PIL import Image
    import io
    pixels=Image.open(io.BytesIO(subprocess.check_output(['ffmpeg','-v','error','-i',str(result),'-frames:v','1','-f','image2pipe','-vcodec','png','-'])))
    assert any(r>80 and g>80 for r,g,b in pixels.convert('RGB').getdata()),'visible preview watermark'
    center=pixels.convert('RGB').crop((100,50,350,200))
    assert not any(r>80 and g>80 for r,g,b in center.getdata()),'preview label must not tile across the image'
    mtime=result.stat().st_mtime_ns;assert make_preview(tmp_path).stat().st_mtime_ns==mtime
