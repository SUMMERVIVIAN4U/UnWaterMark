import json,os,re,time,uuid
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI,UploadFile,File,Form,HTTPException,Request
from fastapi.responses import FileResponse,JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.exception_handlers import request_validation_exception_handler
from starlette.concurrency import run_in_threadpool
from starlette.middleware.trustedhost import TrustedHostMiddleware
from .media import validate_name,inspect_video,validate_mask,MAX_BYTES
from .jobs import JobManager,BASE
from .normalization import prepare_upload,POLICY
ROOT=Path(os.environ.get('VIDEO_REMOVER_RUNTIME',BASE/'runtime')).resolve()

def create_app(root=ROOT):
    root=Path(root);(root/'uploads').mkdir(parents=True,exist_ok=True)
    @asynccontextmanager
    async def lifespan(app):
        app.state.jobs=JobManager(root)
        yield
        app.state.jobs.close()
    app=FastAPI(lifespan=lifespan)
    @app.middleware('http')
    async def same_origin(request,call_next):
        if request.method in {'POST','PUT','DELETE','PATCH'}:
            origin=request.headers.get('origin')
            if origin and origin!=str(request.base_url).rstrip('/'):return JSONResponse({'detail':'仅允许同源请求'},status_code=403)
        response=await call_next(request)
        if request.url.path in {'/','/app.js','/style.css'}:response.headers['Cache-Control']='no-store'
        return response
    app.add_middleware(TrustedHostMiddleware,allowed_hosts=['127.0.0.1','localhost','testserver'])
    def safe(id):
        if not re.fullmatch('[a-f0-9]{32}',id):raise HTTPException(404,'未找到')
        return id
    def upload(id):
        p=root/'uploads'/safe(id)/'upload.json'
        if not p.exists():raise HTTPException(404,'未找到视频')
        return json.loads(p.read_text())
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
    def health():return {'status':'ok','engines':['fast','propainter'],'default_ui_engine':'fast','device':'cpu'}
    @app.get('/api/capabilities')
    def capabilities():return dict(engines=[dict(id='fast',name='OpenCV fast CPU',min_dimension=2,dimension_multiple=2),dict(id='propainter',name='ProPainter CPU',min_dimension=128,dimension_multiple=16)],default_ui_engine='fast',normalization=POLICY,limits=dict(max_bytes=MAX_BYTES,max_audio_streams=1,preview_seconds=30))
    @app.post('/api/uploads')
    async def add_upload(file:UploadFile=File(...)):
        name=Path(file.filename or '').name;validate_name(name,0);id=uuid.uuid4().hex;p=root/'uploads'/id;p.mkdir();source=p/'video';size=0
        try:
            with source.open('wb') as out:
                while chunk:=await file.read(1024*1024):
                    size+=len(chunk);validate_name(name,size);out.write(chunk)
            m=await run_in_threadpool(prepare_upload,source,inspect_video);m.update(id=id,name=name,original_url=f'/api/uploads/{id}/original',url=f'/api/uploads/{id}/video');(p/'upload.json').write_text(json.dumps(m));return m
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
        m=upload(upload_id)
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
    def retry(id:str):job(id);return app.state.jobs.retry(id)
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
    if (BASE/'web').exists():app.mount('/',StaticFiles(directory=BASE/'web',html=True),name='web')
    return app
app=create_app()
