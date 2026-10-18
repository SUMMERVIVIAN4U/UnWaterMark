import json, os, signal, subprocess, sys, threading, time, uuid, fcntl, shlex
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]

def stop_group(proc):
    try:os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError:return
    try:proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:os.killpg(proc.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        proc.wait()
    # Leader exit does not mean its inherited group is empty.
    try:os.killpg(proc.pid,signal.SIGKILL)
    except ProcessLookupError:return
    except PermissionError:pass  # macOS can report EPERM for an already empty group.
    deadline=time.monotonic()+3
    while True:
        rows=subprocess.check_output(['/bin/ps','-axo','pgid=,stat='],timeout=3).decode().splitlines()
        live=any(parts and int(parts[0])==proc.pid and not parts[1].startswith('Z') for row in rows if (parts:=row.split()))
        if not live:return
        if time.monotonic()>=deadline:raise RuntimeError('worker process group still has live descendants')
        time.sleep(.05)

def worker_matches(pid,root,id):
    try:
        command=subprocess.check_output(['/bin/ps','-ww','-p',str(pid),'-o','command='],timeout=3).decode().strip()
        parts=shlex.split(command)
        return parts[-4:]==['-m','app.worker',str(root.resolve()),id] and os.getpgid(pid)==pid
    except (OSError,ValueError,subprocess.SubprocessError):return False

class JobManager:
    def __init__(self,root,command_factory=None):
        self.root=Path(root).resolve();(self.root/'jobs').mkdir(parents=True,exist_ok=True)
        self.runtime_lock=(self.root/'.service.lock').open('a+')
        try:fcntl.flock(self.runtime_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:
            self.runtime_lock.close();raise RuntimeError('运行目录正在被另一个服务使用')
        self.lock=threading.RLock();self.items={};self.active=None;self.active_id=None;self.stopped=False
        self.command_factory=command_factory or (lambda j:[sys.executable,'-m','app.worker',str(self.root),j['id']])
        for p in (self.root/'jobs').glob('*/job.json'):
            j=json.loads(p.read_text());j.setdefault('engine','propainter');self.items[j['id']]=j
            if j['status'] in ('queued','running'):
                pid=j.get('worker_pid')
                if pid and worker_matches(pid,self.root,j['id']):
                    try:os.killpg(pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                self.update(j['id'],status='failed',stage='interrupted',error='服务中断，任务未完成；请重试')
        self.thread=threading.Thread(target=self._loop,daemon=True);self.thread.start()
    def update(self,id,**kw):
        with self.lock:
            j=self.items[id];j.update(kw,updated_at=time.time());p=self.root/'jobs'/id/'job.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(j,ensure_ascii=False));tmp.replace(p);return dict(j)
    def get(self,id):
        with self.lock:
            j=dict(self.items[id]);stage=self.root/'jobs'/id/'stage.json'
            if j['status']=='running' and stage.exists():
                try:j.update(json.loads(stage.read_text()))
                except (OSError,ValueError):pass
            return j
    def create(self,upload_id,mode,mask,engine='propainter'):
        if engine not in {'fast','propainter'}:raise ValueError('无效处理引擎')
        with self.lock:
            if self.stopped:raise ValueError('服务已关闭')
        id=uuid.uuid4().hex;p=self.root/'jobs'/id;p.mkdir()
        (p/'mask.png').write_bytes(mask)
        with self.lock:
            self.items[id]=dict(id=id,upload_id=upload_id,mode=mode,engine=engine,status='queued',stage='queued',error=None,result_url=None,created_at=time.time(),updated_at=time.time())
            return self.update(id)
    def cancel(self,id):
        with self.lock:
            if self.items[id]['status'] not in ('queued','running'):return self.get(id)
            self.update(id,status='canceled',stage='canceled',error=None)
            if self.active_id==id and self.active:stop_group(self.active)
            return self.get(id)
    def retry(self,id):
        j=self.get(id)
        if j['status'] not in ('failed','canceled'):raise ValueError('只有失败或取消的任务可以重试')
        return self.create(j['upload_id'],j['mode'],(self.root/'jobs'/id/'mask.png').read_bytes(),engine=j.get('engine','propainter'))
    def _loop(self):
        while not self.stopped:
            with self.lock:
                if self.stopped:return
                j=next((x for x in self.items.values() if x['status']=='queued'),None)
                if j:
                    id=j['id'];self.update(id,status='running',stage='prepare')
                    log=open(self.root/'jobs'/id/'worker.log','ab')
                    try:
                        self.active=subprocess.Popen(self.command_factory(j),cwd=BASE,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);self.active_id=id
                        self.update(id,worker_pid=self.active.pid);proc=self.active
                    except Exception as e:
                        self.update(id,status='failed',error=str(e));log.close();continue
            if not j:time.sleep(.05);continue
            code=proc.wait()
            try:stop_group(proc)
            except (OSError,RuntimeError,subprocess.SubprocessError) as e:
                log.close()
                with self.lock:
                    self.stopped=True
                    self.update(id,status='failed',stage='failed',error=f'进程清理失败，队列已停止，请关闭服务后检查并重启：{str(e)[:200]}')
                return
            log.close()
            with self.lock:
                if self.items[id]['status']=='running':
                    result=self.root/'jobs'/id/'result.mp4'
                    if code==0 and result.exists():self.update(id,status='succeeded',stage='complete',result_url=f'/api/jobs/{id}/result')
                    else:
                        error=f'处理失败（退出码 {code}）；请重试或检查输入格式'
                        try:
                            detail=json.loads((self.root/'jobs'/id/'workererror.json').read_text())
                            phase=str(detail['phase'])[:40];cause=' '.join(str(detail['cause']).split())[:500]
                            error=f'处理失败（{phase}）：{cause}'
                        except (OSError,ValueError,KeyError,TypeError):pass
                        self.update(id,status='failed',stage='failed',error=error)
                self.active=None;self.active_id=None
    def close(self):
        with self.lock:
            self.stopped=True
            if self.active:
                self.update(self.active_id,status='failed',stage='interrupted',error='服务关闭，任务中断');stop_group(self.active)
        self.thread.join(timeout=5)
        fcntl.flock(self.runtime_lock,fcntl.LOCK_UN);self.runtime_lock.close()
