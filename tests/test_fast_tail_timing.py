"""Container tail duration must not make raw decoder synthesize extra frames."""
import subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.media import inspect_video
from app.fast import repair
from PIL import Image,ImageDraw

def test_fast_preserves_frames_with_extended_last_packet_duration(tmp_path):
    source=tmp_path/'source.mp4';tail=tmp_path/'tail.mp4';out=tmp_path/'out.mp4';mask=tmp_path/'mask.png'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=128x128:r=24','-frames:v','48','-c:v','libx264','-bf','0',str(source)],check=True)
    subprocess.run(['ffmpeg','-v','error','-i',str(source),'-c','copy','-bsf:v',r'setts=duration=if(eq(N\,47)\,7*DURATION\,DURATION)',str(tail)],check=True)
    meta=inspect_video(tail);assert meta['frames']==48 and meta['fps']==24
    im=Image.new('L',(128,128));ImageDraw.Draw(im).rectangle((40,40,55,55),fill=255);im.save(mask)
    repair(tail,mask,out,meta,lambda args:None)
    result=inspect_video(out)
    assert result['frames']==48 and result['fps']==24 and result['duration']==2
