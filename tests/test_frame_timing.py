import json,subprocess,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.media import inspect_video

@pytest.mark.parametrize('fps',['24','30000/1001'])
def test_constant_timestamps_override_incorrect_average(tmp_path,monkeypatch,fps):
    p=tmp_path/'sample.mov'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=s=128x128:r={fps}','-t','2','-c:v','libx264',str(p)],check=True)
    original=subprocess.check_output
    def probe(args,**kw):
        data=original(args,**kw)
        if '-show_frames' in args:
            d=json.loads(data);d['streams'][0]['avg_frame_rate']='723/31';return json.dumps(d).encode()
        return data
    monkeypatch.setattr(subprocess,'check_output',probe)
    m=inspect_video(p)
    assert m['fps_fraction']==fps
    assert m['duration']==pytest.approx(m['frames']/m['fps'])

def test_real_variable_timestamps_still_rejected(tmp_path):
    p=tmp_path/'vfr.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=128x128:r=24','-t','2','-vf',"select='not(eq(mod(n,5),4))'",'-fps_mode','vfr','-c:v','libx264',str(p)],check=True)
    with pytest.raises(ValueError,match='VFR'):inspect_video(p)
