import json,sys,time
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

def store(tmp_path):
    from app.sessions import SessionStore,password_record
    password=tmp_path/'password.json';password.write_text(json.dumps(password_record('test-export-password')))
    return SessionStore(tmp_path,password)

def test_opaque_private_sessions_persist(tmp_path):
    s=store(tmp_path);a=s.create('one');b=s.create('one')
    assert a['owner_id']!=b['owner_id'] and len(a['token'])>=40
    assert not s.get('made-up') and s.get(a['token'])['owner_id']==a['owner_id']
    assert a['token'].encode() not in (tmp_path/'sessions.sqlite3').read_bytes()
    assert store(tmp_path).get(a['token'])['owner_id']==a['owner_id']

def test_unlock_scope_expiry_and_rate_limit(tmp_path):
    from app.sessions import SessionLimit
    s=store(tmp_path);a=s.create('one');b=s.create('two')
    assert not s.unlock(a['token'],'wrong','one')
    assert s.unlock(a['token'],'test-export-password','one')
    assert s.get(a['token'])['export_until']>time.time()
    assert s.get(b['token'])['export_until']==0
    for _ in range(5):assert not s.unlock(b['token'],'wrong','two')
    with pytest.raises(SessionLimit):s.unlock(b['token'],'test-export-password','two')
    with s.connect() as db:db.execute('UPDATE sessions SET expires=0 WHERE owner_id=?',(a['owner_id'],))
    assert s.get(a['token']) is None
