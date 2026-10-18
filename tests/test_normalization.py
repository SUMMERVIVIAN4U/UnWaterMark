import hashlib, io, json, subprocess, sys
from pathlib import Path
import pytest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def ff(*args):
    subprocess.run(['ffmpeg','-v','error','-y','-threads','2',*map(str,args)],check=True,stderr=subprocess.PIPE)

def fixture(tmp_path, audio=True):
    p=tmp_path/'base.mp4'
    args=['-f','lavfi','-i','testsrc2=s=128x96:r=24']
    if audio:args+=['-f','lavfi','-i','sine=frequency=440:sample_rate=48000']
    ff(*args,'-t','2','-c:v','libx264','-c:a','aac',p)
    return p

def prepare(path):
    import app.server as server
    assert hasattr(server,'prepare_upload'), 'separate upload preparation service required'
    return server.prepare_upload(path)

def test_passthrough_preserves_uploaded_bytes(tmp_path):
    p=fixture(tmp_path);before=p.read_bytes();m=prepare(p)
    assert p.read_bytes()==before and m['working_file']==p.name
    n=m['normalization'];assert not n['applied'] and n['original_sha256']==n['working_sha256']==hashlib.sha256(before).hexdigest()

@pytest.mark.parametrize('kind', ['vfr','rotation','sar','video_offset','audio_late','audio_early','odd','hevc'])
def test_real_normalization_keeps_original_and_strict_working(tmp_path,kind):
    from app.media import inspect_video
    p=fixture(tmp_path);source=tmp_path/'source.mp4'
    if kind=='vfr':ff('-i',p,'-vf',"select='not(eq(mod(n,5),4))'",'-fps_mode','vfr','-c:v','libx264','-c:a','copy',source)
    elif kind=='rotation':ff('-display_rotation:v:0','90','-i',p,'-c','copy',source)
    elif kind=='sar':ff('-i',p,'-vf','setsar=2','-c:v','libx264','-c:a','copy',source)
    elif kind=='video_offset':ff('-itsoffset','0.5','-i',p,'-c','copy',source)
    elif kind=='audio_late':ff('-i',p,'-itsoffset','0.5','-i',p,'-map','0:v','-map','1:a','-c','copy',source)
    elif kind=='audio_early':ff('-itsoffset','0.5','-i',p,'-i',p,'-map','0:v','-map','1:a','-c','copy',source)
    elif kind=='odd':ff('-i',p,'-vf','crop=127:95:exact=1','-c:v','libx264','-pix_fmt','yuv444p','-c:a','copy',source)
    else:ff('-i',p,'-c:v','libx265','-threads','2','-x265-params','pools=1:frame-threads=1','-c:a','copy',source)
    before=source.read_bytes();m=prepare(source);working=source.parent/m['working_file'];out=inspect_video(working)
    assert source.read_bytes()==before and working!=source and m['normalization']['applied']
    assert any('重新编码' in text for text in m['normalization']['warnings'])
    assert out['has_audio'] and abs(out['duration']-2)<=1/out['fps']+.05
    assert not out['display_transforms'] and out['sample_aspect_ratio']=='1:1'
    if kind=='vfr':assert out['fps']==30 and any('VFR' in s for s in m['normalization']['warnings'])
    if kind=='rotation':assert (out['width'],out['height'])==(96,128)
    if kind=='sar':assert (out['width'],out['height'])==(256,96)
    if kind=='odd':assert (out['width'],out['height'])==(128,96)
    if kind=='audio_late':
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(working),'-map','0:a:0','-ac','1','-ar','48000','-f','f32le','-'])
        import numpy as np
        samples=np.frombuffer(raw,dtype='<f4');assert abs(samples[:18000]).max()<.01 and abs(samples[30000:40000]).max()>.05

def test_upload_rejects_hdr_and_multiple_audio(tmp_path):
    p=fixture(tmp_path)
    for kind in ['hdr','multiple']:
        source=tmp_path/(kind+'.mp4')
        if kind=='hdr':ff('-i',p,'-vf','setparams=color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc','-c:v','libx264','-c:a','copy',source)
        else:ff('-i',p,'-map','0:v','-map','0:a','-map','0:a','-c','copy',source)
        with pytest.raises(ValueError,match='HDR|音轨'):prepare(source)

def test_explicit_engine_capabilities_cache_and_original(tmp_path):
    from fastapi.testclient import TestClient
    from app.server import create_app
    p=fixture(tmp_path)
    with TestClient(create_app(tmp_path/'runtime')) as c:
        metadata=c.post('/api/uploads',files={'file':('x.mp4',p.read_bytes())}).json()
        mask=io.BytesIO();Image.new('L',(128,96),255).save(mask,format='PNG')
        for engine in [None,'unknown']:
            data={'upload_id':metadata['id'],'mode':'full'}
            if engine:data['engine']=engine
            response=c.post('/api/jobs',data=data,files={'mask':('mask.png',mask.getvalue(),'image/png')})
            assert response.status_code==400 and '引擎' in response.json()['detail']
        assert not c.get('/api/jobs').json()['jobs']
        caps=c.get('/api/capabilities');assert caps.status_code==200 and caps.json()['default_ui_engine']=='fast'
        assert c.get(metadata['original_url']).content==p.read_bytes()
        for path in ['/','/app.js','/style.css']:assert c.get(path).headers['cache-control']=='no-store'

def test_job_openapi_requires_explicit_engine(tmp_path):
    from fastapi.testclient import TestClient
    from app.server import create_app
    with TestClient(create_app(tmp_path)) as client:
        schema=client.get('/openapi.json').json()
        body=schema['paths']['/api/jobs']['post']['requestBody']['content']['multipart/form-data']['schema']['$ref'].rsplit('/',1)[1]
        assert 'engine' in schema['components']['schemas'][body]['required']

@pytest.mark.parametrize('audio', [False, True])
def test_extended_last_frame_hold_is_normalized_without_losing_tail(tmp_path,audio):
    from app.media import inspect_video
    base=tmp_path/'base.mp4';source=tmp_path/'original.mp4'
    args=['-f','lavfi','-i','testsrc2=s=128x96:r=24']
    ff(*args,'-frames:v','48','-c:v','libx264','-bf','0','-c:a','aac',base)
    if audio:
        with_audio=tmp_path/'audio.mp4'
        ff('-i',base,'-f','lavfi','-i','sine=frequency=440:sample_rate=48000','-map','0:v','-map','1:a','-t','3','-c:v','copy','-c:a','aac',with_audio)
        base=with_audio
    ff('-i',base,'-c','copy','-bsf:v',r'setts=duration=if(eq(N\,47)\,12288\,512)',source)
    before=source.read_bytes();m=prepare(source)
    assert m['normalization']['applied'], 'a terminal display hold must not be treated as plain CFR'
    assert m['normalization']['source']['vfr'] and m['fps']==30
    assert m['duration']==pytest.approx(2.958333,abs=1/30)
    assert source.read_bytes()==before
    assert any('末帧' in text for text in m['normalization']['reasons'])
    working=source.parent/m['working_file']
    def last_rgb(path):
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-map','0:v:0','-fps_mode','passthrough','-f','rawvideo','-pix_fmt','rgb24','-'])
        import numpy as np
        return np.frombuffer(raw[-128*96*3:],dtype='uint8').astype(float)
    assert abs(last_rgb(source)-last_rgb(working)).mean()<5
    if audio:
        raw=subprocess.check_output(['ffmpeg','-v','error','-i',str(working),'-map','0:a:0','-ac','1','-ar','48000','-f','f32le','-'])
        import numpy as np
        pcm=np.frombuffer(raw,dtype='<f4');assert len(pcm)/48000>=2.9 and abs(pcm[int(2.7*48000):int(2.8*48000)]).max()>.05
    assert inspect_video(working)['has_audio']==audio


def test_mov_nonterminal_packet_duration_does_not_change_cfr_grid(tmp_path):
    base=tmp_path/'base.mov';source=tmp_path/'original.mov'
    ff('-f','lavfi','-i','testsrc2=s=128x96:r=24','-frames:v','241','-c:v','libx264','-bf','0',base)
    ff('-i',base,'-c','copy','-bsf:v',r'setts=duration=if(eq(N\,239)\,8*DURATION\,DURATION)',source)
    m=prepare(source)
    assert m['frames']==241 and m['fps']==24 and m['duration']==pytest.approx(241/24)
    assert not m['normalization']['applied'] and m['normalization']['original_sha256']==m['normalization']['working_sha256']
