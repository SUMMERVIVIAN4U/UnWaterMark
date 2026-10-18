"""Hosted-only retention coordinated with requests and the worker queue."""
import json,logging,math,re,shutil,threading,time
from starlette.responses import JSONResponse
LOG=logging.getLogger(__name__)

class Retention:
    def __init__(self,manager,seconds=86400,interval=60):
        self.manager=manager;self.seconds=seconds;self.interval=interval
        self.gate=threading.Lock();self.requests=0;self.cleaning=False
        self.stop=threading.Event();self.thread=None

    def enter_request(self):
        with self.gate:
            if self.cleaning:return False
            self.requests+=1;return True

    def leave_request(self):
        with self.gate:self.requests-=1

    def start(self):
        self.sweep()  # Finish startup cleanup before accepting HTTP traffic.
        self.thread=threading.Thread(target=self._loop,name='retention',daemon=True);self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:self.thread.join()

    def _loop(self):
        while not self.stop.wait(self.interval):
            try:self.sweep()
            except Exception:LOG.exception('Retention pass failed; will retry')

    def sweep(self,now=None):
        now=time.time() if now is None else now;cutoff=now-self.seconds
        with self.gate:
            if self.cleaning or self.requests:return
            self.cleaning=True
        def expired(timestamp):
            try:value=float(timestamp);return math.isfinite(value) and value<=cutoff
            except (ValueError,TypeError):return False
        def safe_dir(path):return bool(re.fullmatch('[a-f0-9]{32}',path.name)) and path.is_dir() and not path.is_symlink()
        try:
            m=self.manager
            with m.lock:
                for id,j in list(m.items.items()):
                    if id==m.active_id or j['status'] not in {'succeeded','failed','canceled'} or not expired(j.get('updated_at')):continue
                    folder=m.root/'jobs'/id
                    if not safe_dir(folder):continue
                    try:shutil.rmtree(folder)
                    except OSError:LOG.exception('Could not expire job %s',id);continue
                    del m.items[id]
                referenced={j['upload_id'] for j in m.items.values()}
                for folder in (m.root/'uploads').iterdir():
                    if folder.name in referenced or not safe_dir(folder):continue
                    try:
                        metadata=folder/'upload.json'
                        if metadata.exists():
                            timestamp=json.loads(metadata.read_text()).get('created_at',metadata.stat().st_mtime)
                        else:timestamp=folder.stat().st_mtime
                        if expired(timestamp):shutil.rmtree(folder)
                    except (OSError,ValueError):LOG.exception('Could not expire upload %s',folder.name)
        finally:
            with self.gate:self.cleaning=False

class RetentionRequests:
    """Hold a lease through the full ASGI response, including streamed downloads."""
    def __init__(self,app,state):self.app=app;self.state=state
    async def __call__(self,scope,receive,send):
        retention=getattr(self.state,'retention',None)
        if scope['type']!='http' or retention is None:return await self.app(scope,receive,send)
        if not retention.enter_request():
            return await JSONResponse({'detail':'正在清理到期文件，请稍后重试'},status_code=503,headers={'Retry-After':'2'})(scope,receive,send)
        try:await self.app(scope,receive,send)
        finally:retention.leave_request()
