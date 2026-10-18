import io, json, subprocess, time, os, signal, sys
from pathlib import Path
import pytest
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

@pytest.fixture
def video(tmp_path):
    p=tmp_path/'a.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=64x48:r=24000/1001','-t','0.5','-c:v','libx264','-pix_fmt','yuv420p',str(p)],check=True)
    return p

def test_real_decode_and_rejections(video,tmp_path):
    from app.media import inspect_video, validate_name, validate_mask
    m=inspect_video(video)
    assert m['width']==64 and m['height']==48 and m['frames']==12
    assert abs(m['fps']-24000/1001)<.001
    with pytest.raises(ValueError): validate_name('x.avi',1)
    with pytest.raises(ValueError): validate_name('x.mp4',100*1024*1024+1)
    bad=tmp_path/'bad.mp4';bad.write_bytes(b'bad')
    with pytest.raises(ValueError): inspect_video(bad)
    for size,color in [((64,48),0),((32,24),255)]:
        b=io.BytesIO();Image.new('L',size,color).save(b,format='PNG')
        with pytest.raises(ValueError):validate_mask(b.getvalue(),64,48)

def test_mock_control_failure_retry_restart(tmp_path):
    # Fake subprocess ONLY verifies error/control paths; no inference assertion.
    from app.jobs import JobManager
    mgr=JobManager(tmp_path,command_factory=lambda job:[sys.executable,'-c','raise RuntimeError("injected worker failure")'])
    j=mgr.create('a'*32,'full',b'mask')
    for _ in range(100):
        if mgr.get(j['id'])['status']=='failed':break
        time.sleep(.03)
    assert mgr.get(j['id'])['status']=='failed'
    r=mgr.retry(j['id']);assert r['id']!=j['id']
    mgr.close()
    p=tmp_path/'jobs'/r['id']/'job.json';d=json.loads(p.read_text());d['status']='running';p.write_text(json.dumps(d))
    again=JobManager(tmp_path);assert again.get(r['id'])['status']=='failed';again.close()

def test_mock_running_and_queued_cancel_kills_group(tmp_path):
    # Sleeping fake worker ONLY verifies process-group cancellation.
    from app.jobs import JobManager
    mgr=JobManager(tmp_path,command_factory=lambda j:[sys.executable,'-c','import time;time.sleep(120)'])
    a=mgr.create('a'*32,'full',b'mask');b=mgr.create('a'*32,'full',b'mask')
    for _ in range(100):
        if mgr.active:break
        time.sleep(.02)
    pid=mgr.active.pid
    mgr.cancel(b['id']);mgr.cancel(a['id']);time.sleep(.15)
    assert mgr.get(a['id'])['status']=='canceled' and mgr.get(b['id'])['status']=='canceled'
    with pytest.raises(ProcessLookupError):os.kill(pid,0)
    mgr.close()

def test_http_upload_mask_origin_range_and_dimension_guard(video,tmp_path):
    from fastapi.testclient import TestClient
    from app.server import create_app
    with TestClient(create_app(tmp_path/'runtime')) as c:
        assert c.get('/api/health').status_code==200
        assert c.post('/api/uploads',files={'file':('x.avi',b'bad')}).status_code==400
        assert c.post('/api/uploads',files={'file':('x.mp4',b'bad')}).status_code==400
        assert c.post('/api/uploads',headers={'Origin':'https://evil.example'},files={'file':('x.mp4',b'bad')}).status_code==403
        r=c.post('/api/uploads',files={'file':('x.mp4',video.read_bytes())});assert r.status_code==200
        uid=r.json()['id'];r=c.get(f'/api/uploads/{uid}/video',headers={'Range':'bytes=0-9'});assert r.status_code==206 and len(r.content)==10
        b=io.BytesIO();Image.new('L',(64,48),255).save(b,format='PNG')
        r=c.post('/api/jobs',data={'upload_id':uid,'mode':'preview','engine':'propainter'},files={'mask':('mask.png',b.getvalue(),'image/png')})
        assert r.status_code==400 and '128' in r.json()['detail']

def test_mock_cancel_kills_term_ignoring_descendant(tmp_path):
    # Fake child ignores TERM: entire inherited process group must still die.
    from app.jobs import JobManager
    marker=tmp_path/'childpid'
    child='import signal,time;signal.signal(signal.SIGTERM,signal.SIG_IGN);time.sleep(120)'
    code=f'import subprocess,time; p=subprocess.Popen([{sys.executable!r},"-c",{child!r}]);open({str(marker)!r},"w").write(str(p.pid));time.sleep(120)'
    mgr=JobManager(tmp_path,command_factory=lambda j:[sys.executable,'-c',code]);j=mgr.create('a'*32,'full',b'mask')
    for _ in range(100):
        if marker.exists():break
        time.sleep(.02)
    time.sleep(.1);pid=int(marker.read_text());mgr.cancel(j['id']);time.sleep(.2)
    try:
        for _ in range(50):
            try:os.kill(pid,0)
            except ProcessLookupError:break
            time.sleep(.02)
        else:pytest.fail('descendant survived group cancellation')
    finally:
        try:os.kill(pid,signal.SIGKILL)
        except ProcessLookupError:pass
        mgr.close()

def test_real_preview_preparation_boundary_and_full(tmp_path):
    from app import worker
    assert hasattr(worker,'prepare_video'), 'preparation must independently validate requested source frame count'
    from app.media import inspect_video
    source=tmp_path/'long.mp4'
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=blue:s=128x128:r=2','-t','32','-c:v','libx264',str(source)],check=True)
    meta=inspect_video(source)
    def command(args,cwd=None):subprocess.run(args,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    for mode,count in [('preview',60),('full',64)]:
        result=worker.prepare_video(source,tmp_path/f'{mode}.mp4',meta,mode,command)
        assert result['frames']==count and result['duration']==count/2

def test_http_rejects_untrusted_host(tmp_path):
    from fastapi.testclient import TestClient
    from app.server import create_app
    with TestClient(create_app(tmp_path)) as c:
        assert c.get('/api/health',headers={'Host':'evil.example'}).status_code==400

def test_http_upload_inspection_runs_in_thread(video,tmp_path,monkeypatch):
    import threading
    import app.server as server
    from fastapi.testclient import TestClient
    original=server.inspect_video
    def inspection(path):
        assert threading.current_thread() is not threading.main_thread()
        # AnyIO worker is distinct from the ASGI portal/event-loop thread.
        assert 'AnyIO worker' in threading.current_thread().name
        return original(path)
    monkeypatch.setattr(server,'inspect_video',inspection)
    with TestClient(server.create_app(tmp_path)) as c:
        assert c.post('/api/uploads',files={'file':('x.mp4',video.read_bytes())}).status_code==200

def test_mock_closed_manager_cannot_launch_queued_work(tmp_path):
    from app.jobs import JobManager
    calls=[]
    manager=JobManager(tmp_path,command_factory=lambda job:calls.append(job) or [sys.executable,'-c','pass'])
    manager.close()
    with pytest.raises(ValueError,match='关闭'):manager.create('a'*32,'full',b'fake')
    assert not calls

def test_runtime_lock_refuses_second_manager(tmp_path):
    from app.jobs import JobManager
    first=JobManager(tmp_path)
    try:
        with pytest.raises(RuntimeError,match='使用'):JobManager(tmp_path)
    finally:first.close()
    third=JobManager(tmp_path);third.close()

def test_restart_never_kills_unverified_reused_pid(tmp_path,monkeypatch):
    import app.jobs as jobs
    folder=tmp_path/'jobs'/('b'*32);folder.mkdir(parents=True)
    (folder/'job.json').write_text(json.dumps(dict(id='b'*32,upload_id='a'*32,mode='full',status='running',worker_pid=os.getpid())))
    kills=[]
    monkeypatch.setattr(jobs.os,'killpg',lambda *args:kills.append(args))
    monkeypatch.setattr(jobs.subprocess,'check_output',lambda *args,**kwargs:b'python unrelated.py')
    manager=jobs.JobManager(tmp_path);assert not kills;assert manager.get('b'*32)['status']=='failed';manager.close()

def test_http_recovery_metadata_and_saved_mask(video,tmp_path):
    from fastapi.testclient import TestClient
    from app.server import create_app
    with TestClient(create_app(tmp_path)) as c:
        metadata=c.post('/api/uploads',files={'file':('restore.mp4',video.read_bytes())}).json()
        r=c.get(f"/api/uploads/{metadata['id']}");assert r.status_code==200 and r.json()==metadata
        # Queue stub only prepares persisted edit data; no inference is started.
        manager=c.app.state.jobs
        jid='c'*32;folder=tmp_path/'jobs'/jid;folder.mkdir()
        mask=io.BytesIO();Image.new('L',(64,48),255).save(mask,format='PNG');data=mask.getvalue();(folder/'mask.png').write_bytes(data)
        manager.items[jid]=dict(id=jid,upload_id=metadata['id'],status='canceled',stage='canceled')
        response=c.get(f'/api/jobs/{jid}/mask');assert response.status_code==200 and response.content==data and response.headers['content-type']=='image/png'
        assert c.get('/api/jobs/not-an-id/mask').status_code==404
        assert c.get('/api/uploads/not-an-id').status_code==404
        assert c.get('/api/jobs/'+('d'*32)+'/mask').status_code==404
