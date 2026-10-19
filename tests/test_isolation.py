import io,json,sys,time
from pathlib import Path
import pytest
from PIL import Image
from fastapi.testclient import TestClient
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.sessions import password_record,COOKIE

@pytest.fixture
def clients(tmp_path,monkeypatch):
    from app.server import create_app
    from app.hosting import HostingPolicy
    monkeypatch.setenv('VIDEO_REMOVER_HOSTED','1');monkeypatch.setenv('VIDEO_REMOVER_HOST','private.example')
    password=tmp_path/'password.json';password.write_text(json.dumps(password_record('export-test')))
    monkeypatch.setenv('VIDEO_REMOVER_EXPORT_PASSWORD_FILE',str(password))
    monkeypatch.setattr(HostingPolicy,'check_storage',lambda *a:None)
    application=create_app(tmp_path/'runtime')
    with TestClient(application,base_url='https://private.example') as a:
        b=TestClient(application,base_url='https://private.example')
        for c in (a,b):
            r=c.get('/api/session');assert r.status_code==200
            c.headers['x-csrf-token']=r.json()['csrf']
        yield a,b,application,tmp_path/'runtime'
        b.close()

def seed(application,root,owner,status='succeeded'):
    u='a'*32;j='b'*32
    p=root/'uploads'/u;p.mkdir();(p/'video').write_bytes(b'private original')
    (p/'upload.json').write_text(json.dumps(dict(id=u,owner_id=owner,name='private.mp4',width=160,height=128,fps=24,duration=2,created_at=time.time(),working_file='video')))
    p=root/'jobs'/j;p.mkdir();(p/'result.mp4').write_bytes(b'private clean result');(p/'mask.png').write_bytes(b'private mask')
    item=dict(id=j,owner_id=owner,upload_id=u,engine='fast',mode='full',status=status,created_at=time.time(),updated_at=time.time(),result_url=f'/api/jobs/{j}/result',stage='complete')
    application.state.jobs.items[j]=item;(p/'job.json').write_text(json.dumps(item))
    return u,j

def test_owner_list_all_routes_and_unlock(clients):
    a,b,app,root=clients;owner=app.state.sessions.get(a.cookies[COOKIE])['owner_id'];u,j=seed(app,root,owner)
    assert len(a.get('/api/jobs').json()['jobs'])==1 and b.get('/api/jobs').json()['jobs']==[]
    paths=[f'/api/uploads/{u}',f'/api/uploads/{u}/original',f'/api/uploads/{u}/video',f'/api/jobs/{j}',f'/api/jobs/{j}/mask',f'/api/jobs/{j}/result',f'/api/jobs/{j}/preview']
    for path in paths:
        assert b.get(path).status_code==404,path
        assert b.get(path,headers={'Range':'bytes=0-2'}).status_code==404,path
    for action in ['cancel','retry']:assert b.post(f'/api/jobs/{j}/{action}').status_code==404
    assert a.get(f'/api/jobs/{j}/result').status_code==403
    assert a.get(f'/api/jobs/{j}/result',headers={'Range':'bytes=0-2'}).status_code==403
    assert a.post('/api/export/unlock',json={'password':'wrong'}).status_code==403
    assert b.post('/api/export/unlock',json={'password':'export-test'}).status_code==200
    assert b.get(f'/api/jobs/{j}/result').status_code==404
    assert a.post('/api/export/unlock',json={'password':'export-test'}).status_code==200
    assert a.get(f'/api/jobs/{j}/result').content==b'private clean result'
    assert a.get(f'/api/jobs/{j}/result',headers={'Range':'bytes=0-2'}).status_code==206

def test_bootstrap_csrf_missing_cookie_and_old_records(clients):
    a,b,app,root=clients;u,j=seed(app,root,None)
    assert a.get(f'/api/jobs/{j}').status_code==404
    assert a.get('/api/jobs').json()['jobs']==[]
    assert a.post('/api/export/unlock',json={'password':'export-test'},headers={'x-csrf-token':'bad'}).status_code==403
    assert a.post('/api/export/unlock',json={'password':'export-test'},headers={'Origin':'https://evil.example'}).status_code==403
    a.cookies.clear();assert a.get('/api/jobs').status_code==401
    r=a.get('/');assert r.status_code==200 and '共享任务记录' not in r.text
    r=a.get('/api/session');assert r.status_code==200
    cookie=r.headers['set-cookie'];assert 'HttpOnly' in cookie and 'Secure' in cookie and 'SameSite=lax' in cookie
    assert a.get('/api/session',headers={'Sec-Fetch-Site':'cross-site'}).status_code==403

def test_forged_owner_and_retry_keep_identity(clients,monkeypatch):
    a,b,app,root=clients;owner=app.state.sessions.get(a.cookies[COOKIE])['owner_id'];u,j=seed(app,root,owner,'canceled')
    monkeypatch.setattr('app.server.prepare_upload',lambda *args:dict(width=160,height=128,fps=24,duration=2))
    r=b.post('/api/uploads',data={'owner_id':owner},files={'file':('small.mp4',b'fixture')});assert r.status_code==200
    assert r.json()['owner_id']==app.state.sessions.get(b.cookies[COOKIE])['owner_id']
    assert a.get('/api/uploads/'+r.json()['id']).status_code==404
    mask=io.BytesIO();Image.new('L',(160,128),255).save(mask,format='PNG')
    assert b.post('/api/jobs',data={'upload_id':u,'engine':'fast','mode':'full','owner_id':owner},files={'mask':('mask.png',mask.getvalue())}).status_code==404
    app.state.jobs.command_factory=lambda j:[sys.executable,'-c','pass']
    r=a.post(f'/api/jobs/{j}/retry');assert r.status_code==200 and r.json()['owner_id']==owner
    assert b.get('/api/jobs/'+r.json()['id']).status_code==404

def test_expired_unlock_and_forged_identity(clients):
    a,b,app,root=clients;owner=app.state.sessions.get(a.cookies[COOKIE])['owner_id'];u,j=seed(app,root,owner)
    assert a.post('/api/export/unlock',json={'password':'export-test'}).status_code==200
    with app.state.sessions.connect() as db:db.execute('UPDATE sessions SET export_until=0 WHERE owner_id=?',(owner,))
    assert a.get(f'/api/jobs/{j}/result').status_code==403
    b.cookies.clear();b.cookies.set(COOKIE,owner)
    assert b.get(f'/api/jobs/{j}').status_code==401
    assert b.post('/api/export/unlock',json={'password':'export-test'}).status_code==401
