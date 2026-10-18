import json,os,re,time,uuid,threading
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,UploadFile,File,Form,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse,HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .media import validate_name,inspect_video,validate_mask,MAX_BYTES
from .jobs import JobManager,BASE
from .normalization import prepare_upload,POLICY
from .hosting import HostingPolicy
from .retention import Retention,RetentionRequests
ROOT=Path(os.environ.get('VIDEO_REMOVER_RUNTIME',BASE/'runtime')).resolve()

def create_app(root=ROOT):
    hosted=HostingPolicy.from_env();admission=threading.Lock()
    root=Path(root);(root/'uploads').mkdir(parents=True,exist_ok=True)
    @asynccontextmanager
    async def lifespan(app):
        app.state.jobs=JobManager(root)
        app.state.retention=Retention(app.state.jobs,seconds=hosted.retention_hours*3600,interval=hosted.cleanup_interval_seconds) if hosted.enabled else None
        if app.state.retention:app.state.retention.start()
        try:yield
        finally:
            if app.state.retention:app.state.retention.close()
            app.state.jobs.close()
    app=FastAPI(lifespan=lifespan)
    @app.middleware('http')
    async def same_origin(request,call_next):
        if request.method in {'POST','PUT','DELETE','PATCH'}:
            origin=request.headers.get('origin')
            if origin and origin!=str(request.base_url).rstrip('/'):return JSONResponse({'detail':'仅允许同源请求'},status_code=403)
        guarded=hosted.enabled and request.method=='POST' and (request.url.path in {'/api/uploads','/api/jobs'} or request.url.path.endswith('/retry'))
        if guarded:
            if not admission.acquire(blocking=False):return JSONResponse({'detail':'试用站正在准备其他请求，请稍后再试'},status_code=429)
            try:
                with app.state.jobs.lock:
                    busy=any(j['status'] in ('queued','running') for j in app.state.jobs.items.values())
                if busy:return JSONResponse({'detail':'试用站已有任务，请等待完成后再提交'},status_code=429)
                try:await run_in_threadpool(hosted.check_storage,root)
                except ValueError as exc:return JSONResponse({'detail':str(exc)},status_code=400)
                response=await call_next(request)
            finally:admission.release()
        else:response=await call_next(request)
        if request.url.path in {'/','/index.html','/app.js','/style.css'}:response.headers['Cache-Control']='no-store'
        return response
    hosts=['127.0.0.1','localhost','testserver']
    if hosted.enabled:
        host=os.environ.get('VIDEO_REMOVER_HOST','')
        if not re.fullmatch(r'[a-zA-Z0-9.-]+',host):raise ValueError('Hosted mode requires an exact VIDEO_REMOVER_HOST')
        hosts.append(host)
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=hosts)
    def safe(id):
        if not re.fullmatch('[a-f0-9]{32}',id):raise HTTPException(404,'未找到')
        return id
    def upload(id):
        p=root/'uploads'/safe(id)/'upload.json'
        if not p.exists():raise HTTPException(404,'未找到视频')
        return json.loads(p.read_text())
    def check_hosted_upload(id):
        m=upload(id)
        if hosted.enabled:
            hosted.check_working(m)
            if (root/'uploads'/id/'video').stat().st_size>hosted.max_bytes:raise ValueError('试用站视频不能超过25 MiB')
        return m
    def job(id):
        safe(id)
        try:return app.state.jobs.get(id)
        except KeyError:raise HTTPException(404,'未找到任务')
    @app.exception_handler(RequestValidationError)
    async def invalid_request(request,exc):
        if request.url.path=='/api/jobs' and any(e.get('loc')==('body','engine') and e.get('type')=='missing' for e in exc.errors()):
            return JSONResponse({'detail':'请刷新页面并明确选择处理引擎（fast 或 propainter）'},status_code=400)
        return await request_validation_exception_handler(request,exc)
    @app.exception_handler(ValueError)
    async def invalid(request,exc):return JSONResponse({'detail':str(exc)},status_code=400)
    @app.get('/api/health')
    def health():return {'status':'ok','engines':['fast'] if hosted.enabled else ['fast','propainter'],'default_ui_engine':'fast','device':'cpu'}
    @app.get('/api/capabilities')
    def capabilities():
        result=dict(engines=[dict(id='fast',name='OpenCV fast CPU',min_dimension=2,dimension_multiple=2),dict(id='propainter',name='ProPainter CPU',min_dimension=128,dimension_multiple=16)],default_ui_engine='fast',normalization=POLICY,limits=dict(max_bytes=MAX_BYTES,max_audio_streams=1,preview_seconds=30))
        if hosted.enabled:
            result['engines']=result['engines'][:1];result['hosting']=hosted.public();result['limits']['max_bytes']=hosted.max_bytes
        return result
    @app.post('/api/uploads')
    async def add_upload(file:UploadFile=File(...)):
        name=Path(file.filename or '').name;validate_name(name,0);id=uuid.uuid4().hex;p=root/'uploads'/id;p.mkdir();source=p/'video';size=0
        try:
            with source.open('wb') as out:
                while chunk:=await file.read(1024*1024):
                    size+=len(chunk);validate_name(name,size)
                    if hosted.enabled and size>hosted.max_bytes:raise ValueError('试用站视频不能超过25 MiB')
                    out.write(chunk)
            m=await run_in_threadpool(prepare_upload,source,inspect_video);m.update(id=id,name=name,created_at=time.time(),original_url=f'/api/uploads/{id}/original',url=f'/api/uploads/{id}/video');(p/'upload.json').write_text(json.dumps(m));return m
        except Exception:
            import shutil
            shutil.rmtree(p);raise
    @app.get('/api/uploads/{id}')
    def get_upload_metadata(id:str):return upload(id)
    @app.get('/api/uploads/{id}/video')
    def get_video(id:str):
        m=upload(id);return FileResponse(root/'uploads'/id/m.get('working_file','video'),media_type='video/mp4')
    @app.get('/api/uploads/{id}/original')
    def get_original(id:str):
        m=upload(id);return FileResponse(root/'uploads'/id/'video',filename=m['name'])
    @app.post('/api/jobs')
    async def create_job(upload_id:str=Form(...),mode:str=Form(...),engine:str=Form(...),mask:UploadFile=File(...)):
        if engine not in {'fast','propainter'}:raise ValueError('请刷新页面并明确选择处理引擎（fast 或 propainter）')
        if hosted.enabled and engine!='fast':raise ValueError('试用站仅提供快速模式')
        m=check_hosted_upload(upload_id)
        if engine=='propainter' and (min(m['width'],m['height'])<128 or m['width']%16 or m['height']%16):raise ValueError('模型要求宽高至少 128 像素且均为 16 的倍数；请提供符合尺寸的视频')
        if mode not in {'preview','full'}:raise ValueError('无效处理模式')
        data=await mask.read(16*1024*1024+1)
        if len(data)>16*1024*1024:raise ValueError('蒙版过大')
        validate_mask(data,m['width'],m['height']);return app.state.jobs.create(upload_id,mode,data,engine=engine)
    @app.get('/api/jobs')
    def jobs():return {'jobs':[app.state.jobs.get(id) for id in list(app.state.jobs.items)][::-1]}
    @app.get('/api/jobs/{id}')
    def get_job(id:str):return job(id)
    @app.post('/api/jobs/{id}/cancel')
    def cancel(id:str):job(id);return app.state.jobs.cancel(id)
    @app.post('/api/jobs/{id}/retry')
    def retry(id:str):
        j=job(id)
        if hosted.enabled and j.get('engine','propainter')!='fast':raise ValueError('试用站仅提供快速模式')
        check_hosted_upload(j['upload_id'])
        return app.state.jobs.retry(id)
    @app.get('/api/jobs/{id}/mask')
    def get_job_mask(id:str):
        job(id)
        path=root/'jobs'/id/'mask.png'
        if not path.is_file():raise HTTPException(404,'未找到蒙版')
        return FileResponse(path,media_type='image/png')
    @app.get('/api/jobs/{id}/result')
    def result(id:str):
        j=job(id)
        if j['status']!='succeeded':raise HTTPException(409,'结果尚未完成')
        return FileResponse(root/'jobs'/id/'result.mp4',media_type='video/mp4',filename='removed.mp4')
    if hosted.enabled:
        @app.get('/index.html',response_class=HTMLResponse,include_in_schema=False)
        @app.get('/',response_class=HTMLResponse,include_in_schema=False)
        def hosted_home():
            html=(BASE/'web/index.html').read_text()
            html=html.replace('LOCAL STUDIO','SERVER TRIAL').replace('<body>','<body data-max-bytes="26214400">').replace('本地视频修复','视频修复试用').replace('● 仅本机处理','● 香港服务器 · 密码试用')
            html=html.replace('选择本地快速修补或研究模型处理','使用服务器快速修补').replace('最大 100 MiB','最大 25 MiB · 30 秒 · 长边≤1280 · 总像素≤720p')
            html=html.replace('<option value="propainter">ProPainter · 研究模式</option>','')
            html=re.sub(r'<p class="hint">ProPainter 研究模式：.*?</p>','<p class="hint">试用站仅开快速模式：SDR 8位、1–60 fps、最多一条音轨。VFR 转30 fps，自动处理常见旋转与音画偏移。一次处理一个任务。文件上传到香港服务器；受邀用户共享素材、结果和任务记录，请勿上传敏感内容。</p>',html)
            return html.replace('素材与处理结果保存在本机。','素材与结果保存在香港服务器，受邀用户共享任务记录；任务结束后保留24小时，到期自动清理；未提交的上传也保留24小时。')
    if hosted.enabled:
        @app.get('/app.js',include_in_schema=False)
        def hosted_script():return FileResponse(BASE/'web/app.js',media_type='application/javascript')
        @app.get('/style.css',include_in_schema=False)
        def hosted_style():return FileResponse(BASE/'web/style.css',media_type='text/css')
    elif (BASE/'web').exists():app.mount('/',StaticFiles(directory=BASE/'web',html=True),name='web')
    if hosted.enabled:app.add_middleware(RetentionRequests,state=app.state)
    return app
app=create_app()
