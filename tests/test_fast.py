import io,json,subprocess,sys
from pathlib import Path
import pytest
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def mask_bytes(size=(66,50)):
    im=Image.new('L',size);ImageDraw.Draw(im).rectangle((20,15,35,30),fill=255)
    b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()

def test_engine_persistence_retry_and_legacy(tmp_path):
    from app.jobs import JobManager
    mgr=JobManager(tmp_path,command_factory=lambda j:[sys.executable,'-c','pass'])
    try:
        with pytest.raises(ValueError,match='引擎'):mgr.create('a'*32,'full',b'mask',engine='unknown')
        j=mgr.create('a'*32,'full',b'mask',engine='fast');mgr.update(j['id'],status='canceled')
        assert mgr.retry(j['id'])['engine']=='fast'
        old=mgr.create('a'*32,'full',b'mask');assert old['engine']=='propainter'
    finally:mgr.close()

@pytest.mark.parametrize('mode,count',[('preview',60),('full',64)])
def test_real_fast_worker_preserves_media(tmp_path,mode,count):
    from app.worker import run
    from app.media import inspect_video
    folder=tmp_path/'jobs'/'job';folder.mkdir(parents=True)
    upload=tmp_path/'uploads'/'upload';upload.mkdir(parents=True)
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=66x50:r=2','-f','lavfi','-i','sine=frequency=440','-t','32','-vf','drawbox=x=20:y=15:w=16:h=16:color=white:t=fill','-c:v','libx264','-c:a','aac','-pix_fmt','yuv420p','-f','mp4',str(upload/'video')],check=True)
    (folder/'mask.png').write_bytes(mask_bytes());(folder/'job.json').write_text(json.dumps(dict(upload_id='upload',mode=mode,engine='fast')))
    run(tmp_path,'job')
    m=inspect_video(folder/'result.mp4');assert m['frames']==count and m['width']==66 and m['height']==50 and m['has_audio'] and m['fps']==2
    manifest=json.loads((folder/'manifest.json').read_text());assert manifest['engine']['algorithm']=='INPAINT_TELEA' and manifest['engine']['opencv_version']
    import cv2
    cap=cv2.VideoCapture(str(folder/'result.mp4'));ok,frame=cap.read();cap.release()
    assert ok and frame[22,27,0]>180 and frame[22,27,1]<60 # white patch actually repaired to blue
    assert 'torch' not in sys.modules

def test_fast_api_accepts_dimensions_and_rejects_unknown(tmp_path):
    from app.server import create_app
    from fastapi.testclient import TestClient
    upload=tmp_path/'uploads'/('a'*32);upload.mkdir(parents=True)
    (upload/'upload.json').write_text(json.dumps(dict(width=66,height=50)))
    with TestClient(create_app(tmp_path)) as c:
        c.app.state.jobs.command_factory=lambda j:[sys.executable,'-c','pass']
        for engine,code in [('unknown',400),('fast',200),('propainter',400)]:
            r=c.post('/api/jobs',data=dict(upload_id='a'*32,mode='full',engine=engine),files={'mask':('mask.png',mask_bytes(),'image/png')})
            assert r.status_code==code
            if code==200:assert r.json()['engine']=='fast'

def test_unknown_worker_engine_rejected_before_processing(tmp_path):
    from app.worker import run
    folder=tmp_path/'jobs'/'job';folder.mkdir(parents=True)
    upload=tmp_path/'uploads'/'upload';upload.mkdir(parents=True)
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=66x50:r=24000/1001','-t','0.5','-c:v','libx264','-f','mp4',str(upload/'video')],check=True)
    (folder/'job.json').write_text(json.dumps(dict(upload_id='upload',mode='full',engine='unknown')))
    with pytest.raises(ValueError,match='引擎'):run(tmp_path,'job')


def test_fast_encoder_failure_cleans_decoder(tmp_path,monkeypatch):
    from app.fast import repair
    import app.fast as fast
    p=tmp_path/'video.mp4';m=tmp_path/'mask.png';m.write_bytes(mask_bytes())
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=66x50:r=24000/1001','-t','1','-c:v','libx264',str(p)],check=True)
    from app.media import inspect_video
    popen=fast.subprocess.Popen;children=[]
    def launch(*args,**kwargs):
        process=popen(*args,**kwargs);children.append(process);return process
    monkeypatch.setattr(fast.subprocess,'Popen',launch)
    with pytest.raises((BrokenPipeError,subprocess.CalledProcessError)):
        repair(p,m,tmp_path/'missing'/'out.mp4',inspect_video(p),lambda args:None)
    assert all(child.poll() is not None for child in children)


def test_fast_fractional_frame_rate(tmp_path):
    from app.fast import repair
    from app.media import inspect_video
    p=tmp_path/'video.mp4';m=tmp_path/'mask.png';m.write_bytes(mask_bytes())
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=s=66x50:r=24000/1001','-t','1','-c:v','libx264',str(p)],check=True)
    meta=inspect_video(p);out=tmp_path/'out.mp4';repair(p,m,out,meta,lambda args:None)
    actual=inspect_video(out)
    assert actual['frames']==meta['frames'] and actual['fps_fraction']=='24000/1001'


def test_legacy_saved_job_reload_and_retry_preserves_propainter(tmp_path):
    from app.jobs import JobManager
    jid='b'*32;folder=tmp_path/'jobs'/jid;folder.mkdir(parents=True)
    (folder/'mask.png').write_bytes(mask_bytes())
    (folder/'job.json').write_text(json.dumps(dict(id=jid,upload_id='a'*32,mode='preview',status='canceled',stage='canceled')))
    manager=JobManager(tmp_path,command_factory=lambda j:[sys.executable,'-c','pass'])
    try:
        restored=manager.get(jid)
        assert restored['engine']=='propainter'
        retried=manager.retry(jid)
        assert retried['engine']=='propainter' and retried['mode']=='preview'
        assert json.loads((tmp_path/'jobs'/retried['id']/'job.json').read_text())['engine']=='propainter'
        assert (tmp_path/'jobs'/retried['id']/'mask.png').read_bytes()==mask_bytes()
    finally:manager.close()
