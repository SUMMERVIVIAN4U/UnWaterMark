import json,threading,sys,os
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
NOW=200000.;DAY=86400

def setup(tmp_path):
    from app.retention import Retention
    manager=SimpleNamespace(root=tmp_path,lock=threading.RLock(),items={},active_id=None)
    (tmp_path/'uploads').mkdir();(tmp_path/'jobs').mkdir()
    return manager,Retention(manager,seconds=DAY)

def upload(m,id,age):
    p=m.root/'uploads'/id;p.mkdir();(p/'video').write_bytes(b'private input');(p/'upload.json').write_text(json.dumps({'created_at':NOW-age}))

def job(m,id,uid,age,status='succeeded'):
    p=m.root/'jobs'/id;p.mkdir();(p/'result.mp4').write_bytes(b'private output')
    data=dict(id=id,upload_id=uid,status=status,updated_at=NOW-age)
    (p/'job.json').write_text(json.dumps(data));m.items[id]=data

def test_expired_terminal_jobs_and_unreferenced_upload_deleted(tmp_path):
    m,r=setup(tmp_path);u='a'*32;j='b'*32
    upload(m,u,DAY+10);job(m,j,u,DAY+1)
    r.sweep(now=NOW)
    assert j not in m.items and not (tmp_path/'jobs'/j).exists() and not (tmp_path/'uploads'/u).exists()

def test_active_recent_shared_uploads_and_exact_boundary(tmp_path):
    m,r=setup(tmp_path);u='a'*32;upload(m,u,DAY*2)
    job(m,'b'*32,u,DAY+1);job(m,'c'*32,u,DAY-1)
    for id,status in [('d'*32,'running'),('e'*32,'queued')]:job(m,id,u,DAY*2,status)
    r.sweep(now=NOW)
    assert 'b'*32 not in m.items and set(m.items)=={'c'*32,'d'*32,'e'*32}
    assert (tmp_path/'uploads'/u).exists()

def test_request_download_lease_defers_deletion(tmp_path):
    m,r=setup(tmp_path);u='a'*32;j='b'*32;upload(m,u,DAY+10);job(m,j,u,DAY+1)
    assert r.enter_request()
    r.sweep(now=NOW);assert j in m.items
    r.leave_request();r.sweep(now=NOW);assert j not in m.items

def test_unsubmitted_upload_age_and_legacy_timestamp(tmp_path):
    m,r=setup(tmp_path);upload(m,'a'*32,DAY+1);upload(m,'b'*32,DAY-1)
    p=tmp_path/'uploads'/('c'*32);p.mkdir();f=p/'upload.json';f.write_text('{}');os.utime(f,(NOW-DAY-1,)*2)
    r.sweep(now=NOW)
    assert [p.name for p in (tmp_path/'uploads').iterdir()]==['b'*32]

def test_terminal_worker_still_exiting_is_protected(tmp_path):
    m,r=setup(tmp_path);u='a'*32;j='b'*32;upload(m,u,DAY*2);job(m,j,u,DAY*2,'canceled');m.active_id=j
    r.sweep(now=NOW);assert j in m.items and (tmp_path/'uploads'/u).exists()

def test_cleanup_failure_keeps_record_and_never_follows_symlink(tmp_path,monkeypatch):
    m,r=setup(tmp_path);u='a'*32;j='b'*32;upload(m,u,DAY*2);job(m,j,u,DAY*2)
    import app.retention as module
    def fail(path):raise OSError('injected')
    monkeypatch.setattr(module.shutil,'rmtree',fail)
    r.sweep(now=NOW);assert j in m.items and r.enter_request();r.leave_request()

def test_symlinked_upload_is_not_followed(tmp_path):
    m,r=setup(tmp_path);outside=tmp_path/'outside';outside.mkdir();(outside/'video').write_bytes(b'keep')
    (tmp_path/'uploads'/('a'*32)).symlink_to(outside,target_is_directory=True)
    r.sweep(now=NOW)
    assert (outside/'video').read_bytes()==b'keep'

def test_asgi_lease_lasts_until_stream_completes(tmp_path):
    import asyncio
    from app.retention import RetentionRequests
    m,r=setup(tmp_path);u='a'*32;j='b'*32;upload(m,u,DAY*2);job(m,j,u,DAY*2)
    async def run():
        started=asyncio.Event();finish=asyncio.Event()
        async def streaming(scope,receive,send):
            await send({'type':'http.response.start','status':200,'headers':[]});started.set()
            await finish.wait();await send({'type':'http.response.body','body':b'data'})
        async def send(message):pass
        async def receive():return {'type':'http.request','body':b''}
        request=asyncio.create_task(RetentionRequests(streaming,SimpleNamespace(retention=r))({'type':'http'},receive,send))
        await started.wait();r.sweep(now=NOW);assert j in m.items
        finish.set();await request;r.sweep(now=NOW);assert j not in m.items
    asyncio.run(run())

def test_background_sweeper_runs_periodically(tmp_path):
    import time
    m,r=setup(tmp_path);r.interval=.02;r.start()
    try:
        time.sleep(.04)
        with m.lock:
            upload(m,'a'*32,DAY*2);job(m,'b'*32,'a'*32,DAY*2)
        deadline=time.monotonic()+2
        while time.monotonic()<deadline and (tmp_path/'jobs'/('b'*32)).exists():time.sleep(.01)
        assert not (tmp_path/'jobs'/('b'*32)).exists()
    finally:r.close()
