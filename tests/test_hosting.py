import sys,subprocess
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def app(tmp_path,monkeypatch):
    monkeypatch.setenv('VIDEO_REMOVER_HOSTED','1')
    monkeypatch.setenv('VIDEO_REMOVER_HOST','unwatermark.example.com')
    from app.server import create_app
    return create_app(tmp_path)

def test_hosted_host_origin_capabilities_and_engine(tmp_path,monkeypatch):
    with TestClient(app(tmp_path,monkeypatch),base_url='https://unwatermark.example.com') as c:
        caps=c.get('/api/capabilities');assert caps.status_code==200
        assert caps.json()['hosting']['max_seconds']==30
        assert [e['id'] for e in caps.json()['engines']]==['fast']
        assert c.post('/api/uploads',headers={'Origin':'https://evil.example'},files={'file':('a.mp4',b'x')}).status_code==403
        r=c.post('/api/jobs',data={'engine':'propainter','mode':'full','upload_id':'a'*32},files={'mask':('a.png',b'x')})
        assert r.status_code==400 and '快速' in r.json()['detail']
        assert c.get('/api/health',headers={'host':'evil.example'}).status_code==400
        assert '服务器' in c.get('/').text and '● 仅本机处理' not in c.get('/').text

def test_hosted_media_rejects_bounds_before_decode(tmp_path,monkeypatch):
    import app.normalization as norm
    source=tmp_path/'wide.mp4'
    subprocess.run(['ffmpeg','-v','error','-y','-f','lavfi','-i','color=s=1400x64:r=24','-t','0.2','-c:v','libx264',str(source)],check=True)
    calls=[];original=norm.probe
    def probe(args,path):
        calls.append(args);return original(args,path)
    monkeypatch.setattr(norm,'probe',probe)
    with TestClient(app(tmp_path/'runtime',monkeypatch),base_url='https://unwatermark.example.com') as c:
        r=c.post('/api/uploads',files={'file':('wide.mp4',source.read_bytes())})
        assert r.status_code==400 and '尺寸' in r.json()['detail']
        assert not any('-show_frames' in x for x in calls)
        assert not list((tmp_path/'runtime/uploads').iterdir())

def test_hosted_busy_and_retry_cannot_bypass(tmp_path,monkeypatch):
    with TestClient(app(tmp_path,monkeypatch),base_url='https://unwatermark.example.com') as c:
        mgr=c.app.state.jobs
        mgr.command_factory=lambda j:[sys.executable,'-c','import time;time.sleep(30)']
        old=mgr.create('a'*32,'full',b'x',engine='propainter');mgr.cancel(old['id'])
        r=c.post('/api/jobs/'+old['id']+'/retry');assert r.status_code==400 and '快速' in r.json()['detail']
        active=mgr.create('a'*32,'full',b'x',engine='fast')
        r=c.post('/api/uploads',files={'file':('a.mp4',b'x')});assert r.status_code==429
        mgr.cancel(active['id'])

def test_hosting_policy_rejects_storage_and_unknown_duration(tmp_path,monkeypatch):
    from app.hosting import HostingPolicy
    p=HostingPolicy(enabled=True)
    monkeypatch.setattr('app.hosting.shutil.disk_usage',lambda root:type('Usage',(),{'free':0})())
    with pytest.raises(ValueError,match='空间'):p.check_storage(tmp_path)
    with pytest.raises(ValueError,match='时长'):p.check_stream({'width':128,'height':128,'avg_frame_rate':'24/1'})

def test_hosted_index_alias_has_server_disclosure(tmp_path,monkeypatch):
    with TestClient(app(tmp_path,monkeypatch),base_url='https://unwatermark.example.com') as c:
        text=c.get('/index.html').text
        assert '● 仅本机处理' not in text and '香港服务器' in text

def test_legacy_upload_and_retry_cannot_bypass_hosted_bounds(tmp_path,monkeypatch):
    import io,json
    from PIL import Image
    upload=tmp_path/'uploads'/('a'*32);upload.mkdir(parents=True)
    (upload/'video').write_bytes(b'x')
    (upload/'upload.json').write_text(json.dumps(dict(width=1920,height=1080,duration=45,fps=24)))
    mask=io.BytesIO();Image.new('L',(1920,1080),255).save(mask,format='PNG')
    with TestClient(app(tmp_path,monkeypatch),base_url='https://unwatermark.example.com') as c:
        c.app.state.jobs.command_factory=lambda j:[sys.executable,'-c','import time;time.sleep(30)']
        r=c.post('/api/jobs',data={'engine':'fast','mode':'full','upload_id':'a'*32},files={'mask':('mask.png',mask.getvalue())})
        assert r.status_code==400
        old=c.app.state.jobs.create('a'*32,'full',mask.getvalue(),engine='fast');c.app.state.jobs.cancel(old['id'])
        r=c.post('/api/jobs/'+old['id']+'/retry');assert r.status_code==400

@pytest.mark.parametrize('path',['/index.html/','/%2e/index.html'])
def test_hosted_never_serves_raw_local_index(tmp_path,monkeypatch,path):
    with TestClient(app(tmp_path,monkeypatch),base_url='https://unwatermark.example.com') as c:
        response=c.get(path)
        assert '● 仅本机处理' not in response.text
        assert response.status_code==404 or '香港服务器' in response.text
