import io,json,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image
from test_isolation import clients

def test_poster_owner_and_real_frame(clients):
    a,b,app,root=clients
    from app.sessions import COOKIE
    uid='c'*32;p=root/'uploads'/uid;p.mkdir()
    subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=red:s=128x240:r=24','-t','0.2','-c:v','libx264','-pix_fmt','yuv420p',str(p/'working.mp4')],check=True)
    (p/'upload.json').write_text(json.dumps(dict(id=uid,owner_id=app.state.sessions.get(a.cookies[COOKIE])['owner_id'],working_file='working.mp4',created_at=time.time())))
    url=f'/api/uploads/{uid}/poster'
    assert b.get(url).status_code==404
    r=a.get(url);assert r.status_code==200 and r.headers['content-type']=='image/jpeg'
    im=Image.open(io.BytesIO(r.content));assert im.size==(128,240)
    red,green,blue=im.getpixel((50,50));assert red>200 and green<30
    assert a.get(url).content==r.content
    a.cookies.clear();assert a.get(url).status_code==401
