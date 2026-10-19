"""Hosted browser identities. Export authorization never changes resource ownership."""
import hashlib,hmac,json,secrets,sqlite3,time
from contextlib import contextmanager
from pathlib import Path
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

COOKIE='__Host-unwatermark'
LIFETIME=30*86400
class SessionLimit(Exception):pass

def digest(value):return hashlib.sha256(value.encode()).hexdigest()
def password_record(password):
    salt=secrets.token_hex(16)
    return {'salt':salt,'hash':hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(salt),600000,dklen=64).hex()}

class SessionStore:
    def __init__(self,root,password_file):
        self.path=Path(root)/'sessions.sqlite3'
        self.password=json.loads(Path(password_file).read_text())
        if len(bytes.fromhex(self.password['salt']))!=16 or len(bytes.fromhex(self.password['hash']))!=64:raise ValueError('Invalid export password configuration')
        with self.connect() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS sessions(token TEXT PRIMARY KEY,owner_id TEXT UNIQUE,csrf TEXT,expires REAL,export_until REAL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY,count INTEGER,until REAL);''')
        self.path.chmod(0o600)
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        try:
            with db:yield db
        finally:db.close()
    def limit(self,key,maximum,seconds):
        now=time.time()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('DELETE FROM limits WHERE until<=?',(now,))
            row=db.execute('SELECT count FROM limits WHERE key=?',(key,)).fetchone()
            if row and row['count']>=maximum:raise SessionLimit('请求过于频繁，请稍后再试')
            db.execute('INSERT INTO limits VALUES(?,1,?) ON CONFLICT(key) DO UPDATE SET count=count+1',(key,now+seconds))
    def create(self,ip):
        self.limit('new:'+digest(ip),30,86400)
        token=secrets.token_urlsafe(32);owner=secrets.token_hex(16);csrf=secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE');db.execute('DELETE FROM sessions WHERE expires<=?',(time.time(),))
            if db.execute('SELECT count(*) FROM sessions').fetchone()[0]>=5000:raise SessionLimit('试用站暂时繁忙，请稍后再试')
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,0)',(digest(token),owner,csrf,time.time()+LIFETIME))
        return dict(token=token,owner_id=owner,csrf=csrf,export_until=0)
    def get(self,token):
        if not token or len(token)>128:return None
        with self.connect() as db:row=db.execute('SELECT * FROM sessions WHERE token=? AND expires>?',(digest(token),time.time())).fetchone()
        return dict(row) if row else None
    def unlock(self,token,password,ip):
        if not self.get(token):return False
        self.limit('unlock-ip:'+digest(ip),5,60)
        self.limit('unlock-session:'+digest(token),5,60)
        if not isinstance(password,str) or not 1<=len(password)<=256:return False
        hashed=hashlib.pbkdf2_hmac('sha256',password.encode(),bytes.fromhex(self.password['salt']),600000,dklen=64).hex()
        if not hmac.compare_digest(hashed,self.password['hash']):return False
        with self.connect() as db:db.execute('UPDATE sessions SET export_until=? WHERE token=?',(time.time()+3600,digest(token)))
        return True

class BrowserSessions(BaseHTTPMiddleware):
    def __init__(self,app,state):super().__init__(app);self.state=state
    async def dispatch(self,request,call_next):
        if not request.url.path.startswith('/api/') or request.url.path in {'/api/health','/api/capabilities'}:return await call_next(request)
        store=self.state.sessions
        token=request.cookies.get(COOKIE);session=await run_in_threadpool(store.get,token)
        bootstrap=request.url.path=='/api/session' and request.method=='GET'
        origin=request.headers.get('origin');site=request.headers.get('sec-fetch-site')
        if (origin and origin!=str(request.base_url).rstrip('/')) or site=='cross-site':return JSONResponse({'detail':'仅允许同源请求'},403)
        if not session and not bootstrap:return JSONResponse({'detail':'浏览器身份已失效，请刷新页面重新开始'},401)
        new_token=None
        if not session:
            try:session=await run_in_threadpool(store.create,request.client.host if request.client else 'unknown')
            except SessionLimit as exc:return JSONResponse({'detail':str(exc)},429,headers={'Retry-After':'60'})
            new_token=token=session['token']
        if request.method not in {'GET','HEAD','OPTIONS'} and not hmac.compare_digest(request.headers.get('x-csrf-token',''),session['csrf']):return JSONResponse({'detail':'页面验证已失效，请刷新后重试'},403)
        request.state.identity=session;request.state.session_token=token
        response=await call_next(request)
        response.headers['Cache-Control']='private, no-store'
        if new_token:response.set_cookie(COOKIE,new_token,max_age=LIFETIME,secure=True,httponly=True,samesite='lax',path='/')
        return response
